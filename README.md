# Match-Engine

Fullstack football betting prediction platform with:

- FastAPI backend for ingestion, Elo, walk-forward logistic regression, Groq context scoring, and ROI backtesting.
- Next.js frontend with a premium Vanilla CSS dashboard.

## Git Setup

This project is now initialized as a Git repository with `main` as the default branch.

Suggested remote setup:

```bash
git remote add origin <your-github-repo-url>
git push -u origin main
```

## Backend

```bash
cd /Users/victorbarny/Desktop/match-engine/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Frontend

```bash
cd /Users/victorbarny/Desktop/match-engine/frontend
npm install
cp .env.local.example .env.local
npm run dev
```

## Defaults

- Initial league: English Premier League
- Historical data source: football-data.co.uk
- News/context source: Google News RSS plus Groq summarization

## CI/CD and AWS Deployment

Three GitHub Actions workflows are included:

- `CI` (`.github/workflows/ci.yml`)
  - Runs backend tests (`pytest`)
  - Runs frontend build
- `Deploy Backend ECS` (`.github/workflows/cd-aws.yml`)
  - Builds backend Docker image
  - Pushes image to ECR
  - Deploys backend ECS task definition
- `Deploy Frontend S3` (`.github/workflows/deploy-frontend-s3.yml`)
  - Builds static Next.js site (`frontend/out`)
  - Syncs static files to S3
  - Invalidates CloudFront cache

### AWS resources created

These resources are now provisioned in `us-east-1`:

- ECS cluster: `match-engine-cluster`
- ECS service: `match-engine-backend-service`
- ECR repository: `match-engine-backend`
- Backend ALB DNS: `match-engine-backend-alb-448289033.us-east-1.elb.amazonaws.com`
- Frontend S3 bucket: `match-engine-frontend-590183970118`
- Frontend CloudFront: `d3h21w0k2lv21j.cloudfront.net` (`E3UKL233DTS9JM`)
- Backend API CloudFront (HTTPS): `d3o9qgqn8buh5g.cloudfront.net` (`E2ENDPXBU1KHX8`)

### GitHub Secrets required

Add these repository secrets before running deployments:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION`
- `ECR_BACKEND_REPOSITORY`
- `ECS_CLUSTER`
- `ECS_BACKEND_SERVICE`
- `FRONTEND_S3_BUCKET`
- `FRONTEND_CLOUDFRONT_DISTRIBUTION_ID`
- `NEXT_PUBLIC_API_BASE_URL`

Recommended values:

- `AWS_REGION=us-east-1`
- `ECR_BACKEND_REPOSITORY=match-engine-backend`
- `ECS_CLUSTER=match-engine-cluster`
- `ECS_BACKEND_SERVICE=match-engine-backend-service`
- `FRONTEND_S3_BUCKET=match-engine-frontend-590183970118`
- `FRONTEND_CLOUDFRONT_DISTRIBUTION_ID=E3UKL233DTS9JM`
- `NEXT_PUBLIC_API_BASE_URL=https://d3o9qgqn8buh5g.cloudfront.net`

### Groq integration (backend runtime secret)

Groq is consumed by the backend only. Configure `GROQ_API_KEY` in AWS Secrets Manager and inject it into the ECS task.

- Secret name: `match-engine/groq_api_key`
- ECS task definition: `infra/ecs/backend-task-definition.json` includes a `secrets` mapping for `GROQ_API_KEY`
- ECS execution role must allow `secretsmanager:GetSecretValue` on that secret

If the secret is missing/invalid, backend falls back to neutral context messaging.

### MCP context provider (optional)

The backend supports a pluggable context provider. By default it uses Groq, but you can switch to MCP-backed context:

- `CONTEXT_PROVIDER=groq` (default)
- `CONTEXT_PROVIDER=mcp`

MCP-related env vars in `backend/.env`:

- `MCP_SERVER_URL` - JSON-RPC endpoint for your MCP server (for example a local MCP HTTP bridge)
- `MCP_TOOL_NAME` - tool used for odds/context extraction (default `findEventsAndMarketsByCompetition`)
- `MCP_TIMEOUT_SECONDS` - request timeout for MCP calls

Recommended MCP servers to evaluate for sports enrichment:

- [odds-api-io/odds-api-mcp-server](https://github.com/odds-api-io/odds-api-mcp-server)
- [axc9000/odds-api-mcp-server](https://github.com/axc9000/odds-api-mcp-server)
- [Cloudbet Sports MCP](https://cloudbet.github.io/wiki/en/docs/sports/api/mcp_integration/)
- [google-research-mcp](https://github.com/zoharbabin/google-research-mcp) for news enrichment

### End-to-end flow

1. Push to a branch or open a PR: CI runs automatically.
2. Merge/push backend changes to `main`: backend ECS deploy runs.
3. Merge/push frontend changes to `main`: frontend S3 deploy runs.
4. Verify deployment:
   - backend health: `GET https://d3o9qgqn8buh5g.cloudfront.net/api/health`
   - frontend app: `https://d3h21w0k2lv21j.cloudfront.net`
