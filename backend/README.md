# Match-Engine Backend

## Run

```bash
cd /Users/victorbarny/Desktop/match-engine/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Test

```bash
cd /Users/victorbarny/Desktop/match-engine/backend
PYTHONPATH=. pytest
```

## Notes

- EPL is the default and only enabled league in this first pass.
- Historical CSV data is fetched from football-data.co.uk and stored idempotently in `database.sqlite3`.
- If `GROQ_API_KEY` is missing, the LLM context layer falls back to a neutral adjustment.
- Expensive model snapshots are cached in memory for `SNAPSHOT_TTL_SECONDS` to keep repeated API calls fast.
- `POST /api/refresh` clears that cache and rebuilds the latest snapshot immediately.
