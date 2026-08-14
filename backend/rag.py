import os

from dotenv import load_dotenv
from google import genai
from sqlalchemy.orm import Session

from backend.models import KnowledgeDocument

# =========================================================
# Environment
# =========================================================

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY not found in environment")

client = genai.Client(api_key=api_key)


# =========================================================
# Create embedding
# =========================================================

def create_embedding(text: str):
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config={
            "output_dimensionality": 3072
        }
    )

    return response.embeddings[0].values


# =========================================================
# Search knowledge base
# =========================================================

def search_knowledge(
    query: str,
    db: Session,
    limit: int = 3
):
    query_embedding = create_embedding(query)

    documents = (
        db.query(KnowledgeDocument)
        .order_by(
            KnowledgeDocument.embedding.cosine_distance(
                query_embedding
            )
        )
        .limit(limit)
        .all()
    )

    return documents