# AI Booking Assistant

## Problem
Customers want to ask for what they want in natural language ("a show under
₹2,000 with seats free") instead of navigating filters, and want policy
questions ("can I cancel this?") answered accurately instead of guessing.

## Naive solution (rejected)
Let the LLM answer directly from its training data, or give it a database
connection / raw SQL tool "for flexibility." Rejected because:
- The model would hallucinate seat availability and prices — both change
  every second and must come from the live database, never from the model's
  own knowledge.
- A raw-SQL or direct-DB tool means the model *is* the authorization layer.
  One bad completion (or a prompt-injected one, e.g. from a malicious event
  description) becomes an arbitrary read/write against production data.

## Chosen solution
`app/services/ai/agent_service.py` runs a standard OpenAI-style tool-calling
loop, via Groq's OpenAI-compatible chat-completions API, against a
**fixed set of typed tools** (`app/services/ai/tools.py`), each a thin
wrapper around an *existing* service function:

```
User message
    -> Groq chat-completions API (system prompt + tool schemas + history)
    -> model emits tool_calls (e.g. search_shows, check_availability)
    -> execute_tool() calls catalog_service / hold_service / booking_service
       directly — the same code the REST API uses, so the same business
       rules, locking, and validation apply
    -> tool results fed back as role="tool" messages
    -> repeat (capped at ai_max_tool_iterations) until the model replies in text
```

### Guardrails
1. **Ownership is never model-supplied.** Every tool executes with
   `user_id` taken from the JWT-authenticated session
   (`ToolContext.user_id`), threaded in by the router. Tool JSON schemas
   have no `user_id` field — there's nothing for the model to spoof, and no
   prompt can talk the agent into acting as another user.
2. **No tool executes arbitrary SQL or deletes anything.** The full tool
   surface is 8 functions (`TOOL_SCHEMAS` in `tools.py`); each maps 1:1 to a
   service function that already existed for the REST API.
3. **Irreversible actions require the user to have said yes.** The system
   prompt instructs the model to only call `create_booking_hold`,
   `confirm_and_pay`, or `cancel_booking` after the user has explicitly
   agreed to the specific seats/booking described. This is a prompt-level
   guardrail (not airtight by construction), so it's backstopped by:
4. **Every irreversible tool call — and every failed call — is
   audit-logged** to the existing `audit_log` table with
   `actor = "ai_agent:<user_id>"`, the tool name, arguments, and outcome.
   Nothing the agent does is invisible after the fact; the admin dashboard's
   "AI activity log" surfaces this table filtered to AI actors
   (`GET /api/admin/ai-activity`).
5. **Rate limited** per user (`ai_rate_limit_per_user_per_minute`) using the
   same Redis token-bucket limiter the booking endpoints use.
6. **A hold is not a purchase**, and the system prompt is explicit about
   this distinction so the model doesn't imply money has moved when it
   hasn't.

### Why tool-calling, not a single mega-prompt
Splitting "search," "check availability," "hold," "pay," "cancel," and
"look up policy" into separate tools means each one can be independently
authorized, audited, and rate-limited, and a compromised or confused model
turn can only ever do one narrow, logged thing — not an open-ended action.

## RAG: platform knowledge vs. transactional data
`app/services/ai/rag.py` retrieves passages from static markdown policy
documents (`app/knowledge/*.md`: cancellation, refund/payment, booking
rules & FAQ) via a TF-IDF cosine-similarity search. This is deliberately
**not** a vector database:

| | Chosen (TF-IDF, in-process) | Vector DB (pgvector / dedicated index) |
|---|---|---|
| Corpus size | 3 static docs, dozens of chunks | Justified at hundreds+ documents |
| Update frequency | Edited by a human, rare | Justified when content grows continuously |
| Match type needed | Lexical (policy questions reuse policy vocabulary) | Justified when semantic/synonym matching matters |
| Cost | Zero new infra | New dependency + index maintenance |

If the knowledge base grows, `rag.retrieve()` is the single seam to swap for
an embedding-based implementation — no caller changes.

**Never used for live data.** `search_policies` only ever answers
"what are the rules," and the system prompt tells the model to use
`check_availability` / `get_booking_details` for anything about a specific
seat, price, or booking's current status — RAG and transactional lookups
are separate tools precisely so the model can't conflate a stale policy doc
with a live seat count.

## Persistence
`ChatSession` / `ChatMessage` (Alembic `0002_ai_chat_tables`) store the full
conversation, including raw tool_calls / tool-result messages, per user —
enough to debug a session without re-deriving what happened. **What gets
replayed back to the model across turns is deliberately narrower**: only
plain user/assistant text (`_load_history` in `agent_service.py`). A past
turn's tool_calls/tool_result objects are never resent. This was found the
hard way running against the real Groq API: resending a well-formed
OpenAI-shaped tool_calls history on turn 2 got rejected by the
`openai/gpt-oss-120b` "harmony" chat template with `Tools should have a
name!` — a provider template quirk, not a malformed request. Rather than
special-case one provider's template, every turn's tool round-trip is now
self-contained and discarded once the assistant's text reply is produced;
that reply already carries the substance of what the tools found.

## Trade-offs and future work
- No streaming (single request/response per turn) — simpler to audit and
  reason about; a production system would stream tokens for perceived
  latency.
- The irreversible-action guardrail is prompt-level, not
  cryptographically enforced; the audit log is the safety net, not a
  prevention mechanism. A stricter design would require a second,
  non-LLM confirmation step (e.g. a signed confirmation token) before
  `confirm_and_pay` executes.
- `ai_max_tool_iterations` (default 6) caps a single turn; a deeply
  multi-step request may need to be split across turns by the user.
