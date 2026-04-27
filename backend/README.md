# Match-Engine System Architecture

## 1) Full System Design

The platform is organized as a prediction service architecture with a frontend consumer and a Python backend that owns ingestion, modeling, contextual enrichment, and prediction APIs.

### High-level layers

1. **Client layer (Frontend/UI)**
   - Browser app (allowed by CORS via `FRONTEND_ORIGIN`, plus localhost defaults) calls backend REST endpoints.
   - Consumes prediction snapshots, backtest metrics, matchup breakdowns, and competition/team metadata.

2. **Application/API layer (FastAPI)**
   - Exposes HTTP contracts under `/api/*`.
   - Validates request query inputs and maps internal failures to HTTP responses.
   - Delegates all domain work to pipeline services.

3. **Domain pipeline layer**
   - Runs historical ingestion, feature generation, model validation/training, fixture scoring, and contextual probability adjustment.
   - Produces standardized prediction payloads used by the API layer.

4. **Data + external integration layer**
   - SQLite persistence for ingested matches and ingestion logs.
   - External CSV source (`football-data.co.uk`) for historical and upcoming fixtures.
   - Optional external context signals via Groq and/or MCP provider integration.

---

## 2) Backend Infrastructure

### Runtime stack

- **Framework:** FastAPI
- **Language/runtime:** Python
- **Storage:** SQLite (`database.sqlite3`) with WAL mode enabled
- **ML toolchain:** pandas, numpy, scikit-learn
- **External I/O:** HTTP integrations via `requests`

### Backend module boundaries

- `app/main.py`
  - API entrypoint and route contracts.
  - CORS setup and endpoint orchestration.

- `app/services/pipeline_service.py`
  - Main orchestration service for end-to-end pipeline execution.
  - Snapshot caching with TTL and force-refresh support.
  - Competition/team listing and matchup prediction composition.

- `app/pipeline/data_pipeline.py`
  - Historical CSV source mapping by competition/season.
  - CSV fetching, schema normalization, row hashing, idempotent upserts.
  - Team listing and upcoming fixture sourcing.

- `app/pipeline/model.py`
  - Feature engineering (Elo/form/rest/implied odds edges).
  - Walk-forward validation, calibration, latest model training.
  - Fixture and ad-hoc matchup scoring.

- `app/pipeline/combiner.py`
  - Post-model probability adjustment using context provider output.
  - Confidence tiering and final prediction assembly.

- `app/pipeline/context_provider.py` + `app/pipeline/llm_layer.py`
  - Context abstraction interface.
  - Groq/news-backed provider and MCP-backed provider implementations.
  - Fallback neutral context behavior when external context is unavailable.

- `app/pipeline/backtest.py`
  - Betting edge simulation against bookmaker odds.
  - ROI/win-rate summaries and per-bet traces.

- `app/db.py`
  - DB bootstrap and schema setup.
  - Connection context manager for atomic writes.

- `app/config.py`
  - Runtime configuration and env-driven settings.

### Persistent storage model

1. **`matches` table**
   - Canonical historical/upcoming fixture store.
   - Unique `row_hash` provides idempotent ingestion.
   - Indexed by `(league_code, match_date)` for query performance.

2. **`ingestion_runs` table**
   - Operational observability for per-season ingestion attempts.
   - Captures row counts, success/failure state, and failure reason.

### External integrations

- **Historical/fixture source:** `https://www.football-data.co.uk/.../*.csv`
- **News feed ingestion:** Google News RSS queries per team
- **LLM context engine (optional):** Groq Chat Completions JSON output
- **Alternative context provider (optional):** MCP JSON-RPC tool call

### Configuration-driven infra controls

- `API_HOST`, `API_PORT`
- `FRONTEND_ORIGIN`
- `SNAPSHOT_TTL_SECONDS`
- `GROQ_API_KEY`, `GROQ_MODEL`
- `CONTEXT_PROVIDER` (`groq` or `mcp`)
- `MCP_SERVER_URL`, `MCP_TOOL_NAME`, `MCP_TIMEOUT_SECONDS`

---

## 3) End-to-End Backend Data Flow

1. API request hits an endpoint (`/api/predictions`, `/api/backtest`, `/api/matchup`, etc.).
2. Service checks in-memory snapshot cache (per competition + TTL).
3. On cache miss/refresh:
   - Ingest historical seasons into SQLite (idempotent).
   - Load league history and engineer feature frame.
   - Run walk-forward validation for metrics.
   - Train calibrated model on latest full history.
   - Load upcoming fixtures and score outcomes.
   - Apply context + sanity adjustments and build prediction payload.
   - Run backtest calculations.
4. Snapshot is cached and API returns a trimmed response payload.

---

## 4) API Surface (Backend Contracts)

- `GET /api/health` -> service liveness
- `GET /api/competitions` -> available competition metadata
- `GET /api/teams?competition=...` -> teams for selected competition
- `GET /api/predictions?competition=...&force_refresh=...` -> upcoming predictions + validation metrics
- `GET /api/backtest?competition=...&force_refresh=...` -> historical edge simulation summary
- `GET /api/matchup?competition=...&home_team=...&away_team=...` -> single fixture deep-dive prediction
- `POST /api/refresh?competition=...` -> explicit cache bust + rebuild

---

## 5) Operational Characteristics

- **Cache strategy:** in-memory snapshot cache with lock-protected refresh path.
- **Reliability mode:** external-context failures degrade gracefully to neutral adjustments.
- **Ingestion safety:** deterministic hashing + insert-ignore semantics prevent duplicate match rows.
- **Performance posture:** expensive model pipeline reused across repeated API calls until TTL expiry.
- **Extensibility point:** pluggable context provider abstraction supports Groq or MCP-backed implementations.
