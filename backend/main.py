import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from google import genai

from backend.context import build_contents
from backend.rag import search_knowledge
from backend.database import SessionLocal
from backend.models import Conversation, Message


# =========================================================
# Environment
# =========================================================

load_dotenv()


# =========================================================
# FastAPI
# =========================================================

app = FastAPI(
    title="AI Support Assistant API",
    version="1.1.0"
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "http://localhost:5173",
    "http://localhost:5178",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5178",
    "https://ai-chatboard.up.railway.app",
],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# Gemini
# =========================================================

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY not found")

client = genai.Client(api_key=api_key)

SYSTEM_INSTRUCTION_TEMPLATE = """
You are an AI Support Assistant.

Your responsibilities:

- Understand the user's question.
- Give clear and useful answers.
- Maintain conversation context.
- Use relevant support knowledge when provided.
- Never invent company-specific policies or procedures.
- If support knowledge is unavailable, use your
  general knowledge for normal/general questions.
- Ask a clarification question when necessary.
- Keep responses concise but useful.

{knowledge_instruction}
"""


# =========================================================
# Database Dependency
# =========================================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# =========================================================
# Request Schemas
# =========================================================

class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None


class RenameRequest(BaseModel):
    title: str


# =========================================================
# Home / Health
# =========================================================

@app.get("/")
def home():
    return {
        "message": "AI Support Assistant backend is working"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


# =========================================================
# Shared chat setup
#
# Handles everything that's identical between the plain and
# streaming chat endpoints: validating input, resolving/creating
# the conversation, saving the user message, and assembling the
# trimmed + RAG-augmented prompt to send to Gemini.
# =========================================================

def _prepare_chat(request: ChatRequest, db: Session):
    user_text = request.message.strip()

    if not user_text:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty."
        )

    # ---------------------------------------------------------
    # Resolve or create the conversation
    # ---------------------------------------------------------

    if request.conversation_id is not None:
        conversation = db.get(Conversation, request.conversation_id)

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found."
            )
    else:
        conversation = Conversation(title=user_text[:50])
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    # ---------------------------------------------------------
    # Save the user's message
    # ---------------------------------------------------------

    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=user_text
    )

    db.add(user_message)
    db.commit()

    # ---------------------------------------------------------
    # Load history and build a bounded, summarized context
    # ---------------------------------------------------------

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
        .all()
    )

    contents = build_contents(client, conversation, messages, db)

    # ---------------------------------------------------------
    # RAG lookup (best-effort -- failure shouldn't kill the chat)
    # ---------------------------------------------------------

    try:
        relevant_documents = search_knowledge(user_text, db)
    except Exception as rag_error:
        print("RAG ERROR:", repr(rag_error))
        relevant_documents = []

    if relevant_documents:
        knowledge_context = "\n\n".join(
            document.content for document in relevant_documents
        )

        knowledge_instruction = f"""
Relevant support knowledge was found.

Use the following support knowledge when it is
relevant to the user's question.

Do not contradict the provided support knowledge.

Support Knowledge:

{knowledge_context}
"""
    else:
        knowledge_instruction = """
No relevant support knowledge was found.

Answer the user's question using your general knowledge.

Do NOT say that you cannot answer simply because
the support knowledge base does not contain the
information.

However, do not invent company-specific policies,
procedures, or facts that were not provided.
"""

    system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.format(
        knowledge_instruction=knowledge_instruction
    )

    return conversation, contents, system_instruction


# =========================================================
# Chat (non-streaming)
# =========================================================

@app.post("/chat")
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    try:
        conversation, contents, system_instruction = _prepare_chat(request, db)

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config={"system_instruction": system_instruction}
            )
        except Exception as gemini_error:
            print("GEMINI ERROR:", repr(gemini_error))
            db.rollback()
            raise HTTPException(
                status_code=503,
                detail="The AI service is temporarily unavailable. Please try again."
            )

        if not response.text:
            db.rollback()
            raise HTTPException(
                status_code=502,
                detail="The AI returned an empty response."
            )

        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=response.text
        )

        db.add(assistant_message)
        db.commit()

        return {
            "conversation_id": conversation.id,
            "reply": response.text
        }

    except HTTPException:
        raise

    except Exception as error:
        print("CHAT ERROR:", repr(error))
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="An unexpected server error occurred."
        )


# =========================================================
# Chat (streaming)
#
# Streams the model's reply to the client as it's generated using
# Server-Sent Events, so the UI can render tokens as they arrive
# instead of waiting for the full response. The full reply is
# still persisted to the database once generation completes.
# =========================================================

@app.post("/chat/stream")
def chat_stream(
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    conversation, contents, system_instruction = _prepare_chat(request, db)

    def event_stream():
        full_text = ""

        try:
            stream = client.models.generate_content_stream(
                model="gemini-2.5-flash",
                contents=contents,
                config={"system_instruction": system_instruction}
            )

            for chunk in stream:
                chunk_text = getattr(chunk, "text", None)

                if not chunk_text:
                    continue

                full_text += chunk_text

                payload = json.dumps({
                    "type": "delta",
                    "content": chunk_text,
                    "conversation_id": conversation.id,
                })

                yield f"data: {payload}\n\n"

        except Exception as gemini_error:
            print("GEMINI STREAM ERROR:", repr(gemini_error))
            db.rollback()

            error_payload = json.dumps({
                "type": "error",
                "detail": "The AI service is temporarily unavailable. Please try again.",
            })

            yield f"data: {error_payload}\n\n"
            return

        if not full_text.strip():
            db.rollback()

            error_payload = json.dumps({
                "type": "error",
                "detail": "The AI returned an empty response.",
            })

            yield f"data: {error_payload}\n\n"
            return

        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=full_text
        )

        db.add(assistant_message)
        db.commit()

        done_payload = json.dumps({
            "type": "done",
            "conversation_id": conversation.id,
        })

        yield f"data: {done_payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


# =========================================================
# Get All Conversations
# =========================================================

@app.get("/conversations")
def get_conversations(
    db: Session = Depends(get_db)
):
    try:
        conversations = (
            db.query(Conversation)
            .order_by(Conversation.id.desc())
            .all()
        )

        return [
            {
                "id": conversation.id,
                "title": conversation.title
            }
            for conversation in conversations
        ]

    except Exception as error:
        print("CONVERSATIONS ERROR:", repr(error))
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to load conversations."
        )


# =========================================================
# Get Conversation Messages
# =========================================================

@app.get("/conversations/{conversation_id}/messages")
def get_messages(
    conversation_id: int,
    db: Session = Depends(get_db)
):
    try:
        conversation = db.get(Conversation, conversation_id)

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found."
            )

        messages = (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .all()
        )

        return [
            {
                "role": message.role,
                "content": message.content
            }
            for message in messages
        ]

    except HTTPException:
        raise

    except Exception as error:
        print("MESSAGES ERROR:", repr(error))
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to load conversation messages."
        )


# =========================================================
# Rename Conversation
# =========================================================

@app.patch("/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: int,
    request: RenameRequest,
    db: Session = Depends(get_db)
):
    try:
        conversation = db.get(Conversation, conversation_id)

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found."
            )

        new_title = request.title.strip()

        if not new_title:
            raise HTTPException(
                status_code=400,
                detail="Title cannot be empty."
            )

        conversation.title = new_title[:200]
        db.add(conversation)
        db.commit()

        return {
            "id": conversation.id,
            "title": conversation.title
        }

    except HTTPException:
        raise

    except Exception as error:
        print("RENAME ERROR:", repr(error))
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to rename conversation."
        )


# =========================================================
# Delete Conversation
# =========================================================

@app.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db)
):
    try:
        conversation = db.get(Conversation, conversation_id)

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found."
            )

        db.delete(conversation)
        db.commit()

        return {
            "status": "deleted",
            "conversation_id": conversation_id
        }

    except HTTPException:
        raise

    except Exception as error:
        print("DELETE ERROR:", repr(error))
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to delete conversation."
        )
