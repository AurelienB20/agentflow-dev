# Deployment

The frontend is a static site; the backend is a single FastAPI container. Visitors only open a URL.

## Option A: Guided Demo only (frontend only, zero cost)

1. Import the repository in Vercel, **Root Directory** `frontend`. `vercel.json` sets the build
   (`npm ci && npm run build`, output `dist`).
2. Leave `VITE_API_URL` empty. The site shows *Guided Demo* and labels Live AI as unavailable.

Any static host works (Netlify, GitHub Pages, S3): asset paths are relative (`base: './'`).

## Option B: with Live AI

### Backend on Render

1. New → Blueprint → select the repository (`render.yaml` at the root), or create a *Web Service* with
   runtime Docker, root directory `backend`.
2. Environment variables (dashboard):
   * `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=…` (secret), optionally `LLM_MODEL`.
   * `ALLOWED_ORIGINS=https://<your-vercel-domain>`.
   * Budget and limits (`MAX_COST_PER_WORKFLOW_USD`, `RATE_LIMIT_PER_IP_PER_HOUR`, `QUOTA_PER_SESSION`, …).
3. Health check: `/api/health`. The container listens on `$PORT`.

Render's free plan sleeps when idle; the first request may take ~30 s. Meanwhile the frontend shows the
backend as offline and the Guided Demo still works.

### Frontend on Vercel

Set `VITE_API_URL=https://<your-render-service>.onrender.com` (build-time variable) and redeploy.

### OpenAI instead of Anthropic

`LLM_PROVIDER=openai`, `OPENAI_API_KEY=…`, `LLM_MODEL=<model id>` (required).

## Option C: one VM with Docker

```bash
cp .env.example .env      # set LLM_PROVIDER and the key
docker compose up -d --build
```

nginx serves the frontend on port 8080 and proxies `/api` to the backend on the same origin (no CORS),
with buffering disabled for SSE. Put a TLS reverse proxy (Caddy, Traefik) in front for a public domain.

## Re-recording the Guided Demo

```bash
cd backend
uv run python scripts/record_demos.py          # scripted model, offline
uv run python scripts/record_demos.py --live   # configured LLM (spends tokens)
```

This writes `demo/scenarios/*.json` and `frontend/src/data/recordings/*.json`. Rebuild the frontend.

## Production checklist

* [ ] `ALLOWED_ORIGINS` set to the exact frontend origin (not `*`).
* [ ] API key only in the host's secret store.
* [ ] Spend limit configured on the LLM provider account as a second safety net.
* [ ] `MAX_COST_PER_WORKFLOW_USD`, `RATE_LIMIT_PER_IP_PER_HOUR`, `QUOTA_PER_SESSION` tuned.
* [ ] One backend instance (in-memory run store and rate limiter).
* [ ] For a persistent result cache on Render, attach a disk and point `RESULT_CACHE_PATH` to it
      (without a disk the cache is rebuilt after each redeploy, which only costs the first run again).
