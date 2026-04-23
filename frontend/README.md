# Match-Engine Frontend

```bash
cd /Users/victorbarny/Desktop/match-engine/frontend
npm install
cp .env.local.example .env.local
npm run dev
```

The dashboard calls the FastAPI backend directly from the browser.
Set `NEXT_PUBLIC_API_BASE_URL` to your backend origin if it is not running on `http://127.0.0.1:8000`.

For static hosting (S3 + CloudFront):

```bash
npm run build
```

This generates static files in `out/`.

Current UX:

- Select a supported competition.
- Pick a home team and away team.
- Generate one matchup prediction with probabilities, compact stats, recent form, and Groq context.
- UEFA Champions League is shown as coming soon because the current football-data.co.uk CSV source does not expose that competition in the same way as EPL and Serie A.
