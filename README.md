# Personal Agent Hub v2

Personal Agent Hub v2 is a lightweight Agent Runtime / Harness. It is not a normal chatbot: the LLM decides the next action, while the harness owns the loop, tools, state, trace, memory, policy, and human approval boundary.

## What Is Implemented

- Self-built Agent Loop with `FinalAnswerAction` and `ToolCallAction`
- OpenAI-compatible provider adapter
- Tool Registry, Tool Policy, and Tool Executor
- Built-in tools: `calculator`, `read_file`, `search_files`, `approval_demo`
- Human-in-the-loop approval with persisted pause/resume
- SQLAlchemy persistence layer configured by `DATABASE_URL`
- Alembic-managed schema migrations
- Long-term memory store and portable retrieval boundary
- Structured trace events per run
- Run list/detail API for inspecting historical executions
- FastAPI API and built-in Web UI with Chat, Runs, Trace Timeline, Memory, Approvals, and Tools views
- Dockerfile for deployment

## Architecture

```text
Frontend
  -> FastAPI
  -> AgentRuntime
     -> ContextBuilder
     -> LLMProvider
     -> Action
     -> ToolRegistry / ToolPolicy / ToolExecutor
     -> TraceStore / MemoryStore / ApprovalManager
     -> SQLAlchemy
```

The runtime does not depend on the OpenAI SDK directly. Provider-specific response objects are converted to internal runtime actions in `backend/llm/openai_compatible.py`.

## Agent Loop

1. Create `agent_runs` row and user message.
2. Retrieve relevant long-term memory.
3. Build context.
4. Call OpenAI-compatible LLM with registered tool schemas.
5. Convert provider response into `FinalAnswerAction` or `ToolCallAction`.
6. If final answer, complete run and write task summary memory.
7. If tool call, evaluate policy.
8. If allowed, execute tool, append tool result, continue loop.
9. If approval is required, persist pending approval and pause the run.
10. When approved/rejected, resume from persisted state.

## Tool System

Each tool exposes:

```text
name
description
input_schema
risk_level
execute(arguments)
```

Current tools:

- `calculator`: safe arithmetic evaluator, no `eval`
- `read_file`: reads UTF-8 files inside `WORKSPACE_DIR`
- `search_files`: searches files inside `WORKSPACE_DIR`
- `approval_demo`: WRITE-risk demo tool that triggers human approval

`read_file` and `search_files` reject path traversal outside the configured workspace.

## Policy And Approval

Risk levels:

- `read_only`
- `write`
- `execute`
- `external_side_effect`

Default policy:

- `read_only`: allowed
- `write`, `execute`, `external_side_effect`: approval required

Approval is persisted in `pending_approvals`. The run status becomes `waiting_for_approval`, and approving or rejecting resumes the original run.

## Memory

Long-term memory entries include:

```text
id
type
content
source
metadata
created_at
```

The current retriever uses portable SQLAlchemy filtering. SQLite FTS5 or PostgreSQL full-text search can be added behind the `MemoryRetriever` interface without changing the runtime.

## Trace

Trace events are structured rows, not logs. Events include:

- `run_started`
- `llm_request`
- `llm_response`
- `tool_requested`
- `tool_started`
- `tool_completed`
- `tool_failed`
- `approval_requested`
- `approval_resolved`
- `memory_retrieved`
- `memory_written`
- `run_completed`
- `run_failed`

The Web UI renders these events as a per-run timeline and keeps the raw event payload available under each event for debugging.

## Security Boundary

This project implements policy checks and human approval. It is not an OS-level sandbox.

Current file tools are constrained to `WORKSPACE_DIR`, but future tools such as shell execution or external write APIs need a separate isolation layer.

## Local Setup

Requires Python 3.11+.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env`:

```text
DATABASE_URL=sqlite:///./data/agent.db
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your-key
LLM_MODEL=gpt-4o-mini
WORKSPACE_DIR=.
AGENT_MAX_STEPS=8
```

Run migrations:

```powershell
alembic upgrade head
```

Start:

```powershell
uvicorn backend.main:app --reload --env-file .env
```

For local UI demos without a real model key, set:

```text
LLM_PROVIDER=fake
```

The fake provider is deterministic and only intended to exercise the harness loop, calculator, trace, memory, and approval flow.

Open:

```text
http://127.0.0.1:8000
```

## API Examples

Chat:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/chat `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"message":"帮我计算 123 * 456"}'
```

Trace:

```text
GET /traces/{run_id}
```

Runs:

```text
GET /runs
GET /runs/{run_id}
```

Approvals:

```text
GET /approvals
POST /approvals/{approval_id}/approve
POST /approvals/{approval_id}/reject
```

Memory:

```text
GET /memory
DELETE /memory/{id}
```

Tools:

```text
GET /tools
```

## Database

Local default:

```text
sqlite:///./data/agent.db
```

Production recommendation:

```text
postgresql+psycopg://user:password@host:5432/personal_agent_hub
```

Change only `DATABASE_URL`; runtime modules use SQLAlchemy and do not call `sqlite3` directly.

## Docker

Build:

```bash
docker build -t personal-agent-hub-v2 .
```

Run with SQLite:

```bash
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=sqlite:///./data/agent.db \
  -e LLM_BASE_URL=https://api.openai.com/v1 \
  -e LLM_API_KEY=your-key \
  -e LLM_MODEL=gpt-4o-mini \
  personal-agent-hub-v2
```

For production, use PostgreSQL and provide `DATABASE_URL` as an environment variable.

## Tests

Tests use `FakeLLMProvider`; no real LLM key is required.

```powershell
pytest
```
