"""
Conversation context management.

Naively sending the *entire* message history to the model on every request
doesn't scale: the context window fills up, latency and cost grow with every
turn, and eventually requests fail outright. This module keeps requests
bounded by:

  1. Sending only the most recent N messages verbatim (a sliding window).
  2. Rolling anything older than that into a single running summary, stored
     on the Conversation row, so long-run context isn't lost -- just
     compressed.

The summary is only regenerated when the window actually overflows, so a
short conversation never pays the extra summarization call.
"""

from sqlalchemy.orm import Session

from backend.models import Conversation, Message

# Number of most-recent messages (across both roles) kept verbatim in the
# prompt. Tune this based on your model's context window and expected
# message length.
MAX_RECENT_MESSAGES = 20


def _summarize(client, existing_summary: str, old_messages: list[Message]) -> str:
    """Fold `old_messages` into `existing_summary` using the LLM itself."""

    transcript = "\n".join(
        f"{m.role}: {m.content}" for m in old_messages
    )

    prompt = f"""You are compressing a support chat transcript into a running summary
that will be fed back to yourself as context on later turns. Be dense and factual:
capture the user's goal, key facts they've shared, and anything already resolved or
promised. Do not add commentary or headers -- return only the summary text.

{f"Existing summary:{chr(10)}{existing_summary}{chr(10)}" if existing_summary else ""}
New messages to fold in:
{transcript}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
    )

    return (response.text or existing_summary or "").strip()


def build_contents(client, conversation: Conversation, messages: list[Message], db: Session):
    """
    Build the Gemini `contents` list for `messages`, applying sliding-window
    trimming + rolling summarization so the payload stays bounded.

    Mutates & persists `conversation.summary` when the window overflows.
    """

    if len(messages) > MAX_RECENT_MESSAGES:
        overflow = len(messages) - MAX_RECENT_MESSAGES
        old_messages = messages[:overflow]
        recent_messages = messages[overflow:]

        conversation.summary = _summarize(
            client, conversation.summary or "", old_messages
        )
        db.add(conversation)
        db.commit()
    else:
        recent_messages = messages

    contents = []

    if conversation.summary:
        contents.append({
            "role": "user",
            "parts": [{
                "text": (
                    "[Earlier conversation summary, provided for context "
                    f"only -- do not repeat it back verbatim]\n{conversation.summary}"
                )
            }],
        })
        contents.append({
            "role": "model",
            "parts": [{"text": "Understood, I have that context."}],
        })

    for message in recent_messages:
        contents.append({
            "role": "user" if message.role == "user" else "model",
            "parts": [{"text": message.content}],
        })

    return contents
