# What's new in this pass

Your POC already had the hard parts working (FastAPI + Postgres/pgvector RAG +
Gemini). This pass fills in the pieces the brief calls out as missing, and
gives the UI a real design pass instead of default form styling.

## Backend

**`backend/context.py` (new) — token/length management**
The original `/chat` sent *every* stored message back to the model on every
turn. That's the "conversation memory" the brief wants, but not the
"token/length management" it also asks for — it grows unbounded and eventually
blows the context window. `build_contents()` now:
- Sends only the most recent `MAX_RECENT_MESSAGES` (20) messages verbatim.
- Once a conversation grows past that, folds everything older into a single
  running summary (via Gemini itself), stored on `Conversation.summary`, and
  prepends that summary instead of the raw history. Short conversations never
  pay the extra summarization call.

**Streaming — `POST /chat/stream`**
The brief's chat UI description says "see replies stream in," but the
original endpoint only returned a full JSON blob after the whole reply was
generated. Added a Server-Sent-Events endpoint using
`client.models.generate_content_stream(...)`; the frontend now renders tokens
as they arrive. The non-streaming `/chat` endpoint is left in place too, so
nothing that depended on it breaks. Both endpoints now share the same
`_prepare_chat()` helper (validation, history loading, RAG lookup) instead of
duplicating that logic.

**`DELETE /conversations/{id}`**
Listed in the brief's own API sketch but not implemented. Cascades to that
conversation's messages via the existing `cascade="all, delete-orphan"` on the
`Conversation.messages` relationship.

**`PATCH /conversations/{id}`** (rename)
Not in the original brief, but the sidebar needed *some* way to give a
conversation a better name than "first 50 characters of the first message."

**`Conversation.summary` column + migration**
`backend/migrations/versions/b1c9a7d4e2f0_add_conversation_summary.py` adds
the column the new context-trimming logic needs. Run it with:
```
alembic upgrade head
```

## Frontend

Full visual pass — dark "support desk" theme (`#0a0c11` base, teal `#4fd1c5`
accent) instead of the default light gray/blue admin-panel look, with
Space Grotesk / Inter / JetBrains Mono for headings, body, and metadata
respectively.

- **Streaming rendering**: the assistant bubble fills in live as SSE chunks
  arrive, with a blinking cursor while generating and a three-dot indicator
  before the first token lands.
- **Rename & delete** conversations from the sidebar (hover to reveal). Delete
  is a two-click arm/confirm instead of a native `confirm()` dialog.
- **Lightweight markdown rendering** (`src/markdown.tsx`) for the assistant's
  replies — bold, inline code, fenced code blocks, and simple lists — without
  pulling in a full markdown dependency.
- **Autosizing composer** (textarea instead of a single-line input), Enter to
  send / Shift+Enter for a newline.
- **Error banner** instead of injecting errors as fake chat bubbles, and a
  small "online" status pill in the header.

## Not changed
- LLM provider stays Gemini (`google-genai`), matching what was already
  wired up, rather than swapping to Claude/OpenAI as the brief's generic
  text mentions — happy to swap that if you'd rather standardize on one
  provider.
- Auth/rate limiting/multi-user isolation still aren't in scope here; the
  brief's spec doesn't call for them and neither did the original code.
