# OpsAnalyst Agent — Design

> Status: **Approved decisions D1–D7, revised for the Azure build guide** (Nov 15, 2026)
> Source: the OpsAnalyst build guide (Azure version), kept locally and not in the repo
> Purpose: decide *how* we build it before writing code. We build phase by phase, and each phase must pass its "Done when" check.

---

## 1. The big picture (in plain words)

A user types a business question. The agent:

1. **Looks around** the database (what tables exist, what columns mean).
2. **Looks up definitions** in the glossary ("revenue" means *this* formula here).
3. **Writes SQL.**
4. **Hands the SQL to a safety checker.** If the SQL is unsafe, it's blocked, and the agent gets told why.
5. **Runs the SQL**, as a read-only user who can only see the rows they're allowed to see.
6. **Checks its own result** (is it empty? are there duplicate rows?). If something looks off, it fixes the SQL (at most 2 retries).
7. **Answers** with a summary, the SQL, the table, and its caveats.

Every one of those steps is **recorded** (a "trace"). If an answer turns out to be wrong, a **forensics tool** reads the trace backwards, finds the first bad step, and labels the kind of mistake. That case then becomes a **permanent test**.

```
             ┌─────────────── Trace recorder (every step) ───────────────┐
             │                                                            │
 Question ─► Agent loop ─► Tools ─► Safety pipeline ─► Postgres (read-only, RLS)
             │    ▲                      │
             │    └──── error / result ──┘
             ▼
          Answer ─► "Flag as wrong" ─► Forensics ─► New eval case ─► CI gate
```

**Where it runs:**
- **Phases 0–5: on your laptop.** Postgres runs in Docker, Python runs directly, and the LLM is the regular OpenAI API.
- **Phase 6: on Azure.** Same code. Only the config changes (Azure OpenAI, Azure Postgres, Container Apps).

---

## 2. Design principles (how we keep the code easy to debug)

These rules apply to every file we write. When something breaks, they make it easy to find where.

| # | Rule | Why it matters to you |
|---|---|---|
| 1 | **One file = one job.** Small files with obvious names (`safety/checks.py`, `tools/glossary.py`). | When a query gets blocked by mistake, you know to open `safety/`. |
| 2 | **Plain functions over clever abstractions.** No metaclasses, no deep inheritance, and only one decorator (`@traced`). | You can read any function top to bottom without jumping around. |
| 3 | **Every failure has a name.** Errors use an enum such as `BlockReason.NOT_SELECT` or `BlockReason.UNKNOWN_COLUMN`, not free text. | You can `GROUP BY reason` in SQL and see exactly what's failing. |
| 4 | **Typed data at every boundary.** Pydantic models for tool inputs/outputs, config files and trace records. | Bad data fails *loudly at the edge*, not silently three steps later. |
| 5 | **Fail fast at startup.** All YAML config is loaded and validated when the app starts. | A typo in `access_policy.yaml` stops the app with a clear message instead of causing weird behavior at runtime. |
| 6 | **Plain SQL, no ORM.** We use `pg8000` directly, and only `agent/db.py` touches the driver (see D9). | You're strong in SQL, and what you read in the code is exactly what runs. |
| 7 | **Every log line carries a `trace_id`.** | One ID connects the UI, the API logs and the trace tables. |
| 8 | **Agent code never mentions TPC-H.** Dataset facts live only in `datasets/<name>/`. | Swapping datasets is a config change, not a code change. |
| 9 | **Each phase ends with tests that pass.** | You never build on top of something broken. |
| 10 | **Tests never call a paid API.** Tests use a fake LLM that returns scripted answers. | Tests are free, fast and give the same result every time. |

---

## 3. Key decisions (approved)

### D1. Agent framework → **plain tool-calling loop** (not LangGraph)
- A plain loop is about 60 lines: call the model, run the tool it asked for, append the result, repeat until it calls `final_answer` or hits the step cap.
- **Why:** you can put a breakpoint or a `print` in one place and see every step. It's also easier to explain in an interview ("here's the loop, here are the guardrails").

### D2. LLM provider → **OpenAI API locally, Azure OpenAI on deploy**, one wrapper file
- The rest of the code calls one function in `agent/llm.py`: `call_model(messages, tools) -> ModelResponse`.
- The official `openai` Python package works with both. Config chooses the provider:
  - `LLM_PROVIDER=openai` → uses `OPENAI_API_KEY` (Phases 0–5)
  - `LLM_PROVIDER=azure_openai` → uses the Azure endpoint + deployment name (Phase 6, no code change)
  - `LLM_PROVIDER=fake` → scripted answers for tests, costs $0
- Two model tiers in config, as in the guide: **strong** = `gpt-4.1` (SQL writing) and **cheap** = `gpt-4.1-mini` (judging, simple steps). We confirm current names and prices at the cost checkpoint (Section 4).

### D3. Tracing → **Postgres tables first, Langfuse later**
- Phase 4 starts by writing traces to two simple tables (`ops.traces`, `ops.spans`). Langfuse (via OpenTelemetry) is added afterwards as an *extra exporter*.
- **Why:** if Langfuse breaks, the agent still works and you still have your traces. You debug with SQL:
  `SELECT * FROM ops.spans WHERE trace_id = '...' ORDER BY started_at;`

### D4. Glossary search → **Postgres full-text search + pgvector with a small local embedding model**
- Keyword search finds exact terms. Vectors catch synonyms ("sales" ≈ "revenue"). We combine both (hybrid search).
- Embeddings come from a **local** model, so there are no API calls and no cost, and it works offline.
- **Why:** each half can be tested on its own if results look wrong.

### D5. PII handling → **block, don't mask** (v1), masking optional later
- The guide says PII is "masked unless the role allows it". For v1 we **block** instead. Roles without PII permission can't select `c_phone` / `c_address`; the pipeline returns `BlockReason.PII_NOT_ALLOWED`, and Postgres column permissions back it up.
- **Why:** it's a single rule that's easy to test. Masking needs extra per-role views. We can add it in Phase 8 for the demo if you want.

### D6. Local setup → **Docker Desktop for Postgres**, Python runs directly
- Postgres 16 + pgvector in Docker (`docker compose up`). Python in a virtual environment, so VS Code breakpoints work.
- The full container stack (API + UI + worker) comes in Phase 6.

### D7. Git → **initialize a repo in Phase 0**
- Each phase becomes a clean commit you can roll back to. `.env` is in `.gitignore` from the very first commit.

### D8. Reusing your earlier projects → **copy small pieces, only when we reach them** (new)
- We don't copy whole projects in. When a phase needs something you've built before, you point me to the file. I read it, explain it, and we bring over only the function we need, rewritten in this project's style.

| Your project | What we'd take | Phase |
|---|---|---|
| Helix (hybrid retrieval) | Only the ranking logic that merges keyword + vector results (e.g. reciprocal rank fusion). Helix stores data in ChromaDB, so we don't copy its storage code; this project keeps everything in Postgres/pgvector. | 1 |
| Model Regression Detection | McNemar test + CI workflow for the eval gate | 5 |
| Cost Autopilot | Model router + cost dashboards | 6 (and cost plan) |

### D9. Postgres driver → **pg8000** (pure Python) (added in Phase 0)
- Windows **Smart App Control** on the dev laptop blocks the compiled `psycopg-binary` driver (`DLL load failed … Application Control policy`). numpy and DuckDB load fine.
- `pg8000` has no compiled code, so it isn't blocked, and you can step into it with the debugger. It's somewhat slower, which doesn't matter with results capped at 1,000 rows.
- Only `agent/db.py` imports the driver. If we switch back to psycopg later (e.g. on Linux in Azure), that's the only file that changes.
- ⚠️ Watch for this again when we add compiled libraries (e.g. the local embedding model in Phase 1). We'll test each import before relying on it.

### D10. TPC-H source data → **download pre-generated, shift dates +28 years** (added in Phase 1)
- Smart App Control also blocks DuckDB's `tpch` extension, so `CALL dbgen()` can't run on the laptop. We download DuckDB's pre-generated `tpch-sf1.db` / `tpch-sf10.db` instead. It's the same data with official row counts.
- **All dates shift +28 years** (1992–1998 → 2020–Aug 2026), so "last quarter" means something today. 28 years keeps weekdays and leap days aligned.
- ⚠️ Phase 5 impact: the 22 official TPC-H queries and `tpch_answers()` use the original dates and need the blocked extension. We'll run that step inside a Linux container and shift the query dates by +28 years.

Failure forensics (Phase 4) is **built fresh** here. There's no earlier BASWE code to reuse.
You'll point me to old code when we reach each phase.

---

## 4. Cost control (new)

You asked for approval before every paid API call. This section explains how we keep spending visible and small.

### 4.1 My working rule
Before I run **anything** that calls a paid API (OpenAI, later Azure), I will tell you:
- what I'm about to run and why
- how many model calls it will make
- the **estimated cost**

Then I **wait for your "yes"**. Everything else (tests, database work, local scripts) is free and doesn't need approval.

### 4.2 Built into the code
- **Fake LLM by default.** `LLM_PROVIDER=fake` is the default in `.env.example`. Real calls only happen when you switch it on.
- **Every model call records its cost** (tokens × price from config) in the trace, so you can see exactly where the money went.
- **Hard spending caps in config** (`agent/budget.py`):
  - `MAX_USD_PER_QUESTION` (e.g. $0.25): stops the run with status `BUDGET_EXCEEDED`.
  - `MAX_USD_PER_DAY` (e.g. $2.00): refuses new real calls until the next day.
- **The eval runner asks for confirmation** before a run that uses the real model: "This run = 50 questions ≈ $X. Continue? [y/N]".
- **Embeddings are local** (D4), so they cost $0.

### 4.3 Rough numbers (to check at the cost checkpoint)
Using the prices I last knew (gpt-4.1 ≈ $2 / $8 per 1M input/output tokens, gpt-4.1-mini ≈ $0.40 / $1.60), and assuming one question uses about 10 steps, ~30k input tokens and ~2k output tokens:

| Model | ≈ per question | ≈ 50-question smoke run |
|---|---|---|
| gpt-4.1 | ~$0.08 | ~$4 |
| gpt-4.1-mini | ~$0.015 | ~$0.75 |

These are **estimates only**. We verify current prices before the first real call.

### 4.4 Cost optimization plan (your idea, scheduled after the skeleton)
Once the Phase 2 loop works **on the fake LLM**, we stop and write a short cost plan *before* making real calls in bulk. Ideas to measure:
- Use the cheap model for simple steps and the strong model only for writing SQL (routing).
- Keep the system prompt + tool definitions stable so OpenAI's automatic prompt caching kicks in (cached input is cheaper).
- Cache `list_tables` / `describe_table` results instead of re-sending the same schema.
- Trim tool outputs (e.g. send 20 sample rows to the model, not 1000).
- Run the BIRD benchmark **once** at the end, as the guide says.

---

## 5. Folder structure

```
ops_analyst_agent/
├── DESIGN.md                    ← this file
├── README.md
├── pyproject.toml               ← dependencies + tool settings
├── .env.example                 ← every setting, no secrets (LLM_PROVIDER=fake by default)
├── .gitignore                   ← includes .env
├── docker-compose.yml           ← local Postgres (+ later: api, ui, worker)
├── docker/postgres-init/        ← SQL run once on first Postgres start (enables pgvector)
│
├── agent/                       ← GENERIC. Never mentions TPC-H.
│   ├── config.py                ← loads + validates .env and datasets/<DATASET>/*.yaml
│   ├── db.py                    ← connection pool; run_query(sql, role)
│   ├── llm.py                   ← call_model(); openai / azure_openai / fake
│   ├── budget.py                ← cost per call, per-question + daily caps
│   ├── loop.py                  ← the agent loop (plan → tools → answer)
│   ├── models.py                ← shared Pydantic models (ToolCall, FinalAnswer, …)
│   ├── prompts/
│   │   └── system.md            ← generic system prompt (no dataset facts)
│   ├── tools/
│   │   ├── registry.py          ← tool name → (function, input model, output model)
│   │   ├── schema_tools.py      ← list_tables, describe_table, sample_values
│   │   ├── glossary.py          ← search_glossary
│   │   ├── sql_tools.py         ← run_sql, check_result
│   │   └── answer_tools.py      ← ask_clarifying_question, final_answer
│   ├── safety/
│   │   ├── reasons.py           ← BlockReason enum
│   │   ├── checks.py            ← one small function per check
│   │   └── pipeline.py          ← runs checks in order; stops at first failure
│   ├── tracing/
│   │   ├── spans.py             ← @traced decorator + Span model
│   │   └── store.py             ← writes traces/spans to Postgres
│   └── forensics/
│       ├── taxonomy.py          ← FailureCategory enum (7 types)
│       └── analyzer.py          ← walks a trace backwards, names the first bad step
│
├── datasets/                    ← SPECIFIC. One folder per database.
│   └── tpch/
│       ├── connection.yaml
│       ├── dictionary.yaml
│       ├── glossary.yaml
│       ├── access_policy.yaml
│       ├── views.sql
│       ├── seed/
│       │   ├── download.py      ← pre-generated TPC-H → Parquet (see D10)
│       │   ├── load.py          ← runs the steps below in order; safe to re-run
│       │   ├── 01_tables.sql    ← empty tables
│       │   ├── 02_keys_indexes.sql
│       │   ├── 03_messiness.sql ← test orders, duplicate names, NULLs, migrations log
│       │   └── 04_security.sql  ← roles, PII column grants, row-level security
│       └── evals/
│           ├── business.yaml
│           ├── attacks.yaml
│           └── ambiguous.yaml
│
├── evals/                       ← GENERIC eval runner
│   ├── runner.py                ← asks for cost confirmation before real runs
│   ├── compare.py               ← result-set comparison (order/float tolerant)
│   └── metrics.py
│
├── api/main.py                  ← FastAPI: POST /ask, POST /flag, GET /trace/{id}
├── ui/app.py                    ← Streamlit chat + SQL panel + trace view
├── scripts/profile_dataset.py   ← introspects any schema → draft dictionary.yaml
├── tests/                       ← mirrors agent/; uses the fake LLM only
└── infra/                       ← Phase 6: Azure (Container Apps, Postgres, Key Vault), Locust
```

**How to use this map when debugging:**

| Symptom | Look in |
|---|---|
| A safe query got blocked / an unsafe one got through | `agent/safety/checks.py` |
| Agent picked the wrong table or column | the trace → `agent/tools/schema_tools.py` + `dictionary.yaml` |
| Agent used the wrong formula | `glossary.yaml` → `agent/tools/glossary.py` |
| User saw rows they shouldn't | `access_policy.yaml` + `datasets/tpch/seed/messiness.sql` (RLS) |
| Model call failed / weird response | `agent/llm.py` |
| Unexpected cost / run stopped with `BUDGET_EXCEEDED` | `agent/budget.py` + `ops.spans.cost_usd` |
| Agent looped too long / stopped early | `agent/loop.py` |

---

## 6. The life of one question (step by step)

Example: *"Which 5 suppliers had the most late shipments last quarter?"* asked by role `analyst`.

1. **API** (`api/main.py`) receives `{question, role}`, creates a `trace_id` and calls `run_agent()`.
2. **Loop** (`agent/loop.py`) sends the system prompt, the question and the list of tool definitions to the model.
3. Model calls **`list_tables()`** → sees `v_shipments` ("one row per shipped line item, with `is_late` flag").
4. Model calls **`search_glossary("late shipment")`** → gets "received after committed date". Calls `search_glossary("quarter")` → learns **fiscal quarters start in February**.
5. Model calls **`describe_table("v_shipments")`** → gets columns + notes.
6. Model calls **`run_sql("SELECT s_name, COUNT(*) ...")`**:
   - **Safety pipeline** runs (Section 7). Passes.
   - **Executes** in a transaction as role `analyst` with a 15 s timeout.
   - Returns rows, row count and runtime.
7. Model calls **`check_result(...)`** → no warnings.
8. Model calls **`final_answer(summary, sql, table, chart_spec, confidence, caveats)`**.
9. Loop stops, the trace is saved, and the API returns the answer + `trace_id`.

**Hard limits in the loop:** max **10 steps** total, max **2 SQL retries**, and the **budget caps** from Section 4. Hitting a limit ends the run with a clear status (`STEP_LIMIT`, `RETRY_LIMIT`, `BUDGET_EXCEEDED`), not a crash.

---

## 7. Safety pipeline

An ordered list of checks. Each check is a small function that returns either "OK" or a `Blocked(reason, message)`. The pipeline **stops at the first failure** and sends the message back to the agent so it can fix its SQL.

| Order | Check | Blocks when… | Reason code |
|---|---|---|---|
| 1 | Parse | sqlglot can't parse it | `PARSE_ERROR` |
| 2 | Single statement | more than one statement (`; DROP …`) | `MULTIPLE_STATEMENTS` |
| 3 | SELECT only | INSERT/UPDATE/DELETE/DDL/COPY/etc. | `NOT_SELECT` |
| 4 | No system tables | `pg_catalog`, `information_schema`, … | `SYSTEM_TABLE` |
| 5 | Table allowlist | table not allowed for this role (or doesn't exist) | `TABLE_NOT_ALLOWED` / `UNKNOWN_TABLE` |
| 6 | Column allowlist | column doesn't exist (hallucinated) | `UNKNOWN_COLUMN` |
| 7 | PII | PII column and role lacks permission | `PII_NOT_ALLOWED` |
| 8 | Row limit | *(doesn't block)* adds `LIMIT 1000` to non-aggregated queries | — |
| 9 | Cost check | `EXPLAIN` estimate over the threshold in `access_policy.yaml` | `TOO_EXPENSIVE` |

**Defense in depth.** Even if a check had a bug, the database itself still protects you:
- The agent connects as a login role that **can only read** (no write grants at all).
- Each query runs inside a transaction with `SET LOCAL ROLE <user_role>` and `SET LOCAL statement_timeout = '15s'`.
- **Row-level security** policies in Postgres filter rows by role (e.g. `europe_manager` sees only European customers).

Every block is recorded as a span event with its reason code, which feeds the "blocked queries by reason" dashboard later.

---

## 8. Config files (what each one holds)

All of these are validated by Pydantic models in `agent/config.py` at startup.

**`.env`** (secrets + environment, never committed):
```
LLM_PROVIDER=fake            # fake | openai | azure_openai
OPENAI_API_KEY=...
MODEL_STRONG=gpt-4.1
MODEL_CHEAP=gpt-4.1-mini
MAX_USD_PER_QUESTION=0.25
MAX_USD_PER_DAY=2.00
DATASET=tpch
DATABASE_URL=postgresql://...
# Phase 6 only: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT, ...
```

**`connection.yaml`**: schema name and login role (the URL itself comes from `.env`).

**`dictionary.yaml`**: one entry per table/view:
```yaml
- table: lineitem
  description: One row per item on an order.
  columns:
    - name: l_extendedprice
      description: Quantity × unit price, before discount.
    - name: l_returnflag
      description: "'R' = returned, 'A' = accepted, 'N' = not yet returned."
```

**`glossary.yaml`**: business definitions:
```yaml
- term: revenue
  synonyms: [sales, net sales]
  definition: Sum of extended price after discount, excluding returns and test orders.
  sql: SUM(l_extendedprice * (1 - l_discount))
  filters: ["l_returnflag <> 'R'", "NOT o_is_test"]
```

**`access_policy.yaml`**: roles and limits:
```yaml
defaults:
  row_limit: 1000
  max_explain_cost: 5000000
roles:
  analyst:        { tables: ["*"], pii: false }
  europe_manager: { tables: ["*"], pii: false }   # rows filtered by RLS in Postgres
  admin:          { tables: ["*"], pii: true }
```

---

## 9. Trace storage (Postgres)

Two tables in a separate `ops` schema (so they never mix with business data):

```sql
ops.traces (trace_id, created_at, question, user_role, dataset,
            status, final_sql, total_tokens, cost_usd, latency_ms,
            flagged, eval_score)

ops.spans  (span_id, trace_id, parent_span_id, step_number, name,
            started_at, ended_at, input_json, output_json,
            error, block_reason, model, tokens_in, tokens_out, cost_usd)
```

`@traced` wraps each tool, so instrumenting a tool is one line. If saving a trace fails, we log the error but **never fail the user's question** because of it.

---

## 10. Failure forensics (Phase 4)

`FailureCategory` enum, straight from the guide:
`SCHEMA_LINKING`, `JOIN`, `DEFINITION`, `FILTER_VALUE`, `AGGREGATION`, `HALLUCINATED_SCHEMA`, `ANSWER_MISREAD`.

**How the analyzer works:**
1. Load the trace's spans in order.
2. If a gold SQL exists, compare tables, joins, filters and aggregations between the agent's SQL and the gold SQL. sqlglot makes this structural, not text-based, and it's **free (no LLM)**.
3. Otherwise, ask an LLM judge (cheap model) about each step, **walking backwards** from the answer. *This step costs money, so it follows the approval rule.*
4. Output: `{first_bad_step, category, evidence}`.
5. The user confirms or corrects it, and the case is appended to `datasets/<name>/evals/`.

---

## 11. Phase plan

Each phase ends with a **"Done when"** check. We don't start the next phase until it passes. 💲 marks steps that call a paid API (approval needed first).

### Phase 0: Project setup (½ day)
Git repo, `.gitignore` (with `.env`), `pyproject.toml` (uv, Python 3.12), `.env.example`, Docker Postgres + pgvector, `agent/config.py`, `agent/db.py`, first tests. Other folders are created by the phase that needs them.
**Done when:** `docker compose up` starts Postgres, `pytest` passes, and the first commit is made. **Cost: $0.** ✅ *Done Nov 15, 2026 (8 tests passing).*

### Phase 1: Company database + glossary (2 days)
Split into **1a: database** (✅ built + reviewed Nov 16, 2026: 23 tests passing; date shift, view-level test-order filter and global supplier visibility approved) and **1b: dictionary + glossary + search** (after the review).
*Performance note from 1a: a full-year revenue query takes ~3.5s on SF1 (RLS adds ~0.2s). At SF10 that's ~35s, over the 15s timeout. Planned fix in Phase 6: summary table / indexes.*

Generate TPC-H SF1 (SF10 later) → load into Postgres with keys and indexes → messiness script (views, dirty values, test orders, roles, RLS) → read-only agent role → `profile_dataset.py` → hand-edit dictionary → write glossary (40–60 entries) → local embeddings + full-text search.
**Done when:** row counts match TPC-H SF1, `europe_manager` sees only European customers (tested), the agent role cannot write (tested), and a glossary search for "sales" returns "revenue". **Cost: $0.**

### Phase 2: Agent tools + loop (3 days)
1. Pydantic models → each tool + its tests → `llm.py` (with the fake provider) → `budget.py` → `loop.py` → CLI: `python -m agent.ask "question"`.
2. **Skeleton check:** the full loop runs end to end on the **fake LLM**. Cost: $0.
3. **Cost checkpoint:** we write the cost optimization plan (Section 4.4) and confirm current prices.
4. 💲 First real run: ~10 hand-picked questions on the cheap model (≈ $0.15–$1, confirmed with you first).
**Done when:** the 10 questions return sensible answers, step/retry/budget limits are tested, and the cost per question is printed.

### Phase 3: Safety guardrails (1.5 days)
`reasons.py` → `checks.py` (one test file per check) → `pipeline.py` → wire into `run_sql`. Most testing hands SQL directly to the pipeline (free). 💲 The attack prompts run through the real agent.
**Done when:** every check has passing and failing tests, and the first 15 attack prompts produce **zero** unsafe executions.
**→ This is your showable MVP.**

### Phase 4: Tracing + forensics (3 days)
`ops` tables → `@traced` → store → API + Streamlit trace view → taxonomy → analyzer → "flag as wrong" flow → Langfuse exporter.
**Done when:** any answer can be opened as a full trace, and a deliberately broken question is diagnosed with the right category.

### Phase 5: Evals + CI (3 days)
Eval files → `compare.py` → `runner.py` → metrics → GitHub Actions smoke set → TPC-H 22 → ablations → 💲 BIRD **once**.
**Done when:** one command prints the scorecard, and CI fails a PR that breaks the prompt.
*Note: a CI smoke run on every PR costs money. We decide in the cost plan whether it runs on every PR or only on PRs labeled `run-evals`.*

### Phase 6: Deploy to Azure + observe + load test (2.5 days)
1. **Open the Azure account only now**, because the $200 free credit lasts just 30 days. **Set budget alerts the same day** ($25 and $50).
2. Azure Database for PostgreSQL Flexible Server (`vector` extension allowed), loaded with SF10 from Parquet in Blob Storage.
3. Azure Container Apps for API, worker and UI; images in Azure Container Registry; HTTPS built in.
4. Secrets in Key Vault via managed identity (no keys in code).
5. Switch `LLM_PROVIDER=azure_openai` (config change only).
6. Dashboards + alerts → 💲 Locust load test (10/25/50 users) → fix first bottleneck → re-run.
7. Write down the monthly cost; stop the Postgres server between demos.
*Fallback (from the guide): if Container Apps slows us down, run the same Docker Compose stack on one Azure VM.*
**Done when:** the live URL works, budget alerts are set, and you have a before/after load-test table.

### Phase 7: Incident drill (1 day) · Phase 8: Polish (2 days)
As described in the build guide.

---

## 12. What we're deliberately NOT doing (to keep it simple)

- No ORM, no async-everything. Synchronous code first. We go async only if the load test proves we need it.
- No LangGraph (see D1).
- No microservices. One Python package, one API, one UI.
- No caching until the cost plan or the load test shows we need it.
- No masking in v1 (see D5).
- No Azure account until Phase 6.

---

## 13. Open items

1. **D8 reuse:** you'll point me to old project code when we reach the phase that needs it.
2. **GitHub:** repo is https://github.com/mohamedchouiki97-pixel/opsanalyst_agent. Pushing happens only when you say so.
