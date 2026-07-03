# Gideon Architecture & Code Review

*Scope: full `src/` tree at commit `699c202`. Stack: Python 3.10, py-cord, aiohttp, SQLite, multi-provider LLM (OpenRouter / OpenAI / AI Horde).*

> Note: the review request mentioned a "Slack bot" — Gideon is a **Discord** bot built on py-cord. All findings below are Discord-specific.

---

## TL;DR — Top 6 highest-impact changes

| # | Change | Impact | Effort |
|---|--------|--------|--------|
| 1 | **Finish the tool-calling loop** — tool results are currently never fed back to the model | Correctness of your flagship feature | Medium |
| 2 | **Move cog loading out of `on_ready`** — it re-runs on every gateway reconnect | Stability (duplicate cogs/listeners) | Small |
| 3 | **Stop blocking the event loop with sync SQLite** — WAL + `asyncio.to_thread` (or aiosqlite) | Latency under concurrent load | Medium |
| 4 | **Delete dead code** — `from.py`, `image_commands.py`, `cloudflare_image_commands.py`, the 350-line `detect_user_intent` prompt | -1,500 LOC, less confusion | Small |
| 5 | **Shared `aiohttp.ClientSession`** — 18 call sites create a new session per request | Latency (TCP+TLS handshake per LLM call) | Small |
| 6 | **Pin dependencies, drop unused ones** (`dnspython`, `feedparser`, `Pillow`), replace `pytz` with stdlib `zoneinfo` | Security/reproducibility | Small |

---

## 1. Architecture & Structure

### 1.1 Framework & versions

- `requirements.txt` pins nothing (`py-cord>=2.4.0`, `aiohttp`, …). py-cord is at 2.6.x; an unpinned `>=` means every deploy may pull a different, untested version. Pin exact versions (see §4).
- `Dockerfile` uses `python:3.10-slim`. 3.10 is in security-only maintenance; move to `python:3.12-slim` — you also get `asyncio` speedups and stdlib `zoneinfo`/`tomllib` for free. No code changes required beyond the pytz swap in §4.
- py-cord's cog/slash-command model is used correctly overall. The main structural issues are *where* things happen, not the framework.

### 1.2 `on_ready` is doing lifecycle work it must not do (`src/bot.py:77-287`)

`on_ready` fires **every time the gateway reconnects**, not once. Today it: initializes the state manager, seeds personas, loads all cogs, syncs commands, and starts the dashboard. On a reconnect (which happens routinely on long-running bots) `bot.load_extension` will raise `ExtensionAlreadyLoaded` for every cog — you're protected only by the blanket `try/except`, and any partial re-init can double-register listeners.

**Fix:** do one-time setup before `run()` and keep `on_ready` for logging only:

```python
# src/bot.py
async def main():
    async with bot:
        state = BotStateManager()
        await state.initialize_state()
        state.set_model_manager(bot.model_manager)
        bot.state_manager = state
        bot.webhook_sender = WebhookSender(bot)

        for cog in COGS:
            bot.load_extension(cog)

        await bot.start(DISCORD_TOKEN)

@bot.event
async def on_ready():
    logger.info("Logged in as %s (%s)", bot.user.name, bot.user.id)

if __name__ == "__main__":
    asyncio.run(main())
```

Command syncing also belongs behind an explicit admin action (you already have `/admin sync`), not every startup — global sync is rate-limited and slow.

### 1.3 Two competing dependency-injection patterns

- Most cogs read `bot.state_manager` / `bot.openrouter_client` (good).
- `ThreadCommands` instead calls `BotStateManager()` (relying on the singleton `__new__`) **and constructs its own private `OpenRouterClient`** (`thread_commands.py:19-20`), bypassing the DB-hot-swapped API keys set up in `on_ready`. If an admin rotates the OpenRouter key via the dashboard, threads keep using the stale `.env` key.

**Fix:** delete the singleton machinery in `BotStateManager.__new__` and pass dependencies explicitly; cogs take them from `bot`. One access pattern, no hidden global.

### 1.4 Business logic in the wrong layer

- `src/bot.py:320-444` — ~120 lines of reminder *delivery* logic (timezone parsing, client selection, AI message generation, Discord error handling) live inside a `tasks.loop` in the entrypoint module. Move to a `ReminderService` (or into `reminder_commands.py`) so bot.py is wiring only.
- `state_manager.clear_channel_history` (`state_manager.py:435-449`) writes raw SQL against `db_manager._conn`, bypassing the entire database-manager layer it sits on. Add `MessageManager.delete_channel_messages()` and call that.

### 1.5 The `DatabaseManager` facade is 480 lines of pure delegation

`src/utils/database/core.py` re-wraps every method of 11 sub-managers one-to-one. Every new DB method must be written twice. Expose the managers as public attributes and delete the wrappers:

```python
class DatabaseManager:
    def __init__(self, db_name="gideon_state.db"):
        ...
        self.config = ConfigManager(conn)
        self.reminders = ReminderManager(conn)
        self.memory = MemoryManager(conn)
        # callers: db.reminders.add_reminder(...) instead of db.add_reminder(...)
```

### 1.6 No provider interface

The three LLM clients are duck-typed on `send_message_with_history`, but signatures and capabilities differ (only OpenRouter honours `tools`, `web_search`, `response_format`; OpenAI/AI Horde silently swallow them via `**kwargs`). Define an explicit protocol so gaps are visible:

```python
from typing import Protocol

class LLMProvider(Protocol):
    supports_tools: bool
    supports_vision: bool

    async def chat(self, messages: list[dict], *, model: str,
                   system_prompt: str | None = None,
                   images: list[dict] | None = None,
                   tools: list[dict] | None = None) -> "ChatResult": ...
```

…and make `ChatResult` a small dataclass (`content`, `tool_calls`, `error`) instead of the current "string, or dict, or string starting with ⚠️" union (see §2.3).

### 1.7 Dead code to delete

| File / code | Why it's dead |
|---|---|
| `src/from.py` | Invalid module name (`from` is a keyword, unimportable); imports `DISCORD_TOKEN` from `bot.py` which doesn't export it |
| `src/cogs/image_commands.py`, `src/cogs/cloudflare_image_commands.py` | Never in the cog list in `bot.py` — superseded by `unified_image_commands` |
| `MentionCommands.detect_user_intent` + its ~350-line prompt (`mention_commands.py:49-443`) | Replaced by native tool calling; nothing calls it |
| `INTENT_DETECTION_MODEL` / `INTENT_CONFIDENCE_THRESHOLD` plumbing | Marked deprecated in config; only feeds the dead method above |

That's roughly 1,500 lines removable with zero behaviour change.

---

## 2. Code Quality

### 2.1 Sync SQLite calls block the event loop

`sqlite3.connect(..., check_same_thread=False)` with synchronous calls sprinkled through async handlers means **every** message in **every** channel does several blocking DB round-trips on the event loop (`on_message` → `check_and_rotate_session` → `get_channel_history` → `add_to_channel_history`). At current scale it works; under bursty load it serializes everything the bot does, including heartbeats.

Minimal fix (no new dependency), plus WAL for concurrent readers:

```python
# core.py __init__
self._conn.execute("PRAGMA journal_mode=WAL;")
self._conn.execute("PRAGMA synchronous=NORMAL;")

# state_manager — wrap hot-path calls:
async def get_channel_history(self, channel_id, limit=None):
    limit = limit if limit is not None else self.max_channel_history
    return await asyncio.to_thread(
        self.db_manager.messages.get_channel_history, str(channel_id), limit)
```

(A fuller migration is `aiosqlite`, but `to_thread` + WAL gets 90 % of the benefit for 5 % of the churn.)

Related: `on_message` records **every message in every channel the bot can see** into SQLite (`mention_commands.py:1116-1125`), even channels where Gideon never speaks. That is write amplification *and* a privacy footprint. Consider only recording history for channels with any bot activity/config, or a channel allowlist.

### 2.2 Concrete bug: hours passed as a message count

`thread_commands.py:599` — `get_discord_thread_history(thread_id, limit=self.state.get_time_window_hours())` passes the *time window in hours* (default 48) as the *message-count limit*. The comment even admits it ("fixes the TypeError"). Should be `hours_limit=...` or use the same limit logic as channels.

### 2.3 Errors as sentinel strings

Clients return `f"⚠️ API Error: ..."` strings, and callers do `response.startswith("⚠️")` (in `mention_commands`, `chat_commands`, `thread_commands`, `memory_service`…). Failure modes: a legitimate model response starting with ⚠️ is treated as an error; a missed check stores API error text into conversation history, which then gets replayed to the model as context. Raise a `ProviderError` exception (or return the `ChatResult` dataclass from §1.6) and handle it at the cog boundary once.

### 2.4 One `aiohttp.ClientSession` per request — 18 call sites

Every LLM call, image generation, and URL fetch builds a new session (new connection pool, new TLS handshake). Create one session per client at startup and reuse it:

```python
class OpenRouterClient:
    def __init__(self, ...):
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120))
        return self._session
```

This also fixes the **missing request timeout** — today a hung OpenRouter request holds the typing indicator forever.

### 2.5 Copy-pasted chunking, model parsing, and fallback flows

- The 2000-char chunker `[response[i:i+max_length] for i in range(...)]` appears **9 times**. It also splits mid-word and mid-code-block. Extract once, split on boundaries:

```python
# src/utils/discord_fmt.py
def chunk_message(text: str, limit: int = 2000) -> list[str]:
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks or [""]
```

- `provider, model_name = model_id_full.split('/', 1)` with an identical `try/except ValueError` fallback appears ~10 times → `state.resolve_model(channel_id) -> tuple[str, str]`.
- `_handle_image_generation_fallback` and the search fallback in `mention_commands` re-implement the whole "get prompt → get history → call LLM → chunk → send" pipeline. Extract a single `respond_conversationally(message, channel_id, prefix="")` helper.
- `MentionCommands.on_message` is ~280 lines. After extracting the helpers above it decomposes naturally into `_gather_context`, `_run_tool_loop`, `_send_reply`.

### 2.6 Datetime handling

Reminders are stored as **naive** datetimes in whatever `TZ` says (default `America/New_York`), and compared against naive "now" reconstructed the same way (`bot.py:333-344`). This breaks on DST transitions (reminders fire an hour off, or a 2:30 AM reminder becomes unrepresentable) and whenever `TZ` changes between write and read. Store **aware UTC** (`datetime.now(timezone.utc)`), render with Discord's `<t:...>` tags (which you already use — they localize client-side, so no server TZ is needed at all).

### 2.7 Smaller items

- `logging.basicConfig` is called at import time inside `openrouter_client.py` — library modules must not configure root logging; do it once in `__main__`.
- `bot.py` mixes `print()` and `logger` — pick the logger.
- Vision support is substring matching (`"gpt-4" in model`) — OpenRouter's `/models` response includes `architecture.modality`; you already fetch it in `get_available_models`, so use that instead of the hardcoded list.
- The Claude image path in `openrouter_client.py:82-91` invents an `<image ... base64>` XML tag that is not a real API format — via OpenRouter, Claude accepts the same OpenAI-style `image_url` content array. Delete the special case.
- `on_message` filters `message.content.startswith('/')` to skip slash commands — slash commands never arrive as messages, so the check is dead.

---

## 3. Features

### 3.1 Native tool calling — **finish the loop** (highest-impact item in this review)

Tool calling exists (`tool_registry.py`, `mention_commands.py:1255-1328`) but the loop is truncated:

1. Tool results are appended to `conversation_context` and then **thrown away** — `response = None` and the follow-up LLM call is explicitly skipped (`mention_commands.py:1321-1323`). The model never sees tool output, so it can't synthesize an answer, chain tools, or recover from a tool error. Each tool instead sends its own Discord message, which is the old intent-dispatch behaviour wearing a new hat.
2. `TOOL_CALLING_MAX_ITERATIONS` is configured, stored in the DB, surfaced in the dashboard… and never read by the executor. Only one round ever runs.
3. Tool executors return status strings like `"Image generation completed"` — useless to the model even if the loop were closed. They should return the *data* (calculation result, reminder time, image URL) and let the model phrase the reply.
4. Assistant/tool turns are never persisted to history, so the next message's context is missing what just happened.

Target shape:

```python
async def run_tool_loop(client, context, *, model, system_prompt, images,
                        tool_context, max_iterations) -> str:
    tools = get_tool_definitions()
    for _ in range(max_iterations):
        result = await client.chat(context, model=model,
                                   system_prompt=system_prompt,
                                   images=images, tools=tools)
        if not result.tool_calls:
            return result.content

        context.append({"role": "assistant",
                        "content": result.content or "",
                        "tool_calls": result.tool_calls})
        for tc in result.tool_calls:
            output = await execute_tool(
                tc["function"]["name"],
                json.loads(tc["function"].get("arguments") or "{}"),
                tool_context)
            context.append({"role": "tool",
                            "tool_call_id": tc["id"],
                            "content": output})   # data, not a status line
        images = None  # only send attachments on the first round

    # Iteration budget exhausted — force a text answer
    result = await client.chat(context, model=model,
                               system_prompt=system_prompt, tool_choice="none")
    return result.content
```

And replace the 11-branch `if/elif` dispatcher in `tool_registry.py` with decorator registration, so a tool is one self-contained unit:

```python
_TOOLS: dict[str, Callable] = {}
TOOL_DEFINITIONS: list[dict] = []

def tool(schema: dict):
    def wrap(fn):
        TOOL_DEFINITIONS.append({"type": "function", "function": schema})
        _TOOLS[schema["name"]] = fn
        return fn
    return wrap

@tool({"name": "calculate", "description": "...", "parameters": {...}})
async def calculate(args: dict, ctx: dict) -> str:
    value = safe_eval(args["expression"])      # sympy — already a dependency
    return f"{args['expression']} = {value}"   # data for the model

async def execute_tool(name, args, ctx) -> str:
    fn = _TOOLS.get(name)
    if fn is None:
        return f"Error: unknown tool '{name}'"
    try:
        return await fn(args, ctx)
    except Exception as e:
        logger.exception("Tool %s failed", name)
        return f"Error: {e}"
```

Side-effect tools (image gen, polls) can keep posting their own embeds — they just *also* return a short factual result ("Image generated and posted: <prompt>") so the model knows what happened.

### 3.2 RAG / memory — you have the right minimal core; two gaps

The existing design (session rotation → LLM summary → summaries injected into the system prompt, `memory_service.py` + `memory_manager.py`) **is** the correct minimal implementation. Don't add a vector DB yet. Two real gaps:

1. **Rotation only triggers on inactivity.** A channel that chats continuously never rotates, and since history is capped at `max_channel_history=35`, everything older silently falls off with **no summary ever written**. Add a size-based trigger: when history exceeds N messages, summarize the oldest chunk and trim, keeping the recent tail verbatim:

```python
async def maybe_compact_history(channel_id, state, clients, *,
                                max_messages=35, keep_tail=15):
    history = state.get_channel_history(channel_id, limit=max_messages + 1)
    if len(history) <= max_messages:
        return
    head, tail = history[:-keep_tail], history[-keep_tail:]
    summary = await _summarize_history(head, channel_id, state, clients)
    if summary:
        state.add_channel_memory(channel_id, summary, len(head),
                                 conversation_start=_parse_timestamp(head[0].get("timestamp")))
    state.trim_channel_history_before(channel_id, tail[0]["timestamp"])
```

2. **No retrieval.** All memories are injected every time, capped at 10, oldest-first — old-but-relevant context gets pruned while irrelevant recent summaries always ride along. The minimal retrieval step that costs nothing new: **SQLite FTS5** (built into the stdlib sqlite3 you already use — no embeddings, no service):

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
USING fts5(summary, content=CHANNEL_MEMORY, content_rowid=memory_id);
```

```python
def search_memories(self, channel_id: str, query: str, limit: int = 3):
    sql = """SELECT m.* FROM memory_fts f
             JOIN CHANNEL_MEMORY m ON m.memory_id = f.rowid
             WHERE f.memory_fts MATCH ? AND m.channel_id = ?
             ORDER BY rank LIMIT ?;"""
    return self._cursor().execute(sql, (query, channel_id, limit)).fetchall()
```

Then `_build_memory_context` becomes "3 most recent summaries + top-3 FTS matches for the current message". If you later want semantic recall, `sqlite-vec` slots into the same table without changing the architecture.

### 3.3 Performance at current scale

- Shared HTTP session (§2.4) and WAL + `to_thread` (§2.1) are the two real wins.
- `on_message` currently does: rotation check (reads full history) → `add_to_channel_history` → `get_channel_history` again. Cache the read: fetch once, append in memory, persist once.
- `check_reminders_task` runs a `tasks.loop(minutes=1)` polling query — fine, and cheap with the existing `idx_reminders_due_timestamp` index. No change needed.

---

## 4. Dependencies & Stack

Current `requirements.txt` audit:

| Package | Status | Recommendation |
|---|---|---|
| `py-cord>=2.4.0` | Active fork, but slower release cadence than discord.py | Pin `py-cord==2.6.*`. Staying on py-cord is fine (you use `SlashCommandGroup`/`bot.sync_commands` idioms); migrating to discord.py is a rewrite of command plumbing — not worth it now |
| `aiohttp` | unpinned | pin |
| `python-dotenv` | fine | pin |
| `dnspython` | **no imports anywhere** | remove |
| `feedparser` | **no imports anywhere** (RSS summarization never landed) | remove |
| `Pillow` | **no imports anywhere** ("potential image processing") | remove |
| `pytz` | superseded by stdlib `zoneinfo` (Py ≥3.9) | remove; `pytz.timezone(tz)` → `zoneinfo.ZoneInfo(tz)`, drop `.localize()` for `datetime(..., tzinfo=ZoneInfo(tz))` |
| `sympy` | used only for calculator tool | keep (safe eval is exactly its job) |
| `beautifulsoup4` | used in `url_commands` | keep, pin |
| `openai>=1.0.0` | used for DALL-E + OpenAI chat | pin `openai==1.*` |
| `cryptography>=41` | Fernet key storage | pin **and keep current** — this one gets CVEs |

Suggested replacement `requirements.txt` (or better, adopt `uv`/`pip-tools` with a lockfile):

```
py-cord==2.6.1
aiohttp==3.11.*
python-dotenv==1.0.*
sympy==1.13.*
beautifulsoup4==4.12.*
openai==1.*
cryptography==44.*
```

Base image: `python:3.12-slim`. Also add a non-root `USER` to the Dockerfile and a `HEALTHCHECK` if the dashboard is enabled.

---

## Suggested sequencing

1. **Week 1 (small, safe):** delete dead code (§1.7); pin/prune dependencies (§4); shared HTTP session + timeouts (§2.4); WAL pragma; fix `thread_commands.py:599` limit bug; move cog loading out of `on_ready` (§1.2).
2. **Week 2 (feature-complete tool calling):** close the tool loop with iteration budget + result feedback + persisted tool turns (§3.1); decorator-based registry; tools return data.
3. **Week 3 (memory):** size-based compaction + FTS5 retrieval (§3.2); stop recording history in channels the bot doesn't participate in (§2.1).
4. **Ongoing refactors as files are touched:** `ChatResult`/exceptions instead of ⚠️-strings (§2.3); extract chunker + model-resolution helpers (§2.5); DI cleanup for `ThreadCommands` (§1.3); UTC-aware reminders (§2.6).
