# PetPulse Core Engine (FastAPI)

Python/FastAPI replacement for the n8n `PetPulse AI - Core Engine` workflow. WhatsApp is the entire
UI — one webhook receives every customer *and* vet message, and a single LLM agent (tool-calling loop)
decides what to do: save data, run triage, book a vet session, file a document, etc. See
`/Users/kes/.claude/plans/typed-coalescing-iverson.md` for the full architecture writeup.

## Setup

```bash
cp .env.example .env   # fill in the real values below
docker build -t petpulse-backend .
docker run -p 8000:8000 --env-file .env -v "$(pwd)/credentials:/app/credentials" petpulse-backend
```

Or locally (needs Python 3.10+ — the codebase uses `X | Y` union type hints throughout):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Credentials you need to provide

| Variable | Where to get it |
|---|---|
| `WHATSAPP_ACCESS_TOKEN` | Meta Business/App dashboard — system-user permanent token for the WhatsApp Cloud API |
| `WHATSAPP_PHONE_NUMBER_ID` | Meta dashboard, defaults to the existing PetPulse number |
| `WHATSAPP_VERIFY_TOKEN` | Any string you choose; must match what you register in Meta's webhook config |
| `WHATSAPP_APP_SECRET` | Meta App dashboard — optional but recommended, enables `X-Hub-Signature-256` verification |
| `OPENAI_API_KEY` | platform.openai.com |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | Supabase project settings — same project the n8n workflow already uses, no migration needed |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Path to a service-account JSON key (put the file under `credentials/`, which is git-ignored) |
| `GOOGLE_CALENDAR_ID` | The calendar to book into — must be explicitly shared with the service account's `client_email` ("Make changes to events"); defaults to the service account's own `primary` calendar, which is fine for local testing but is NOT the real shared team calendar |

`ffmpeg` must be on the host for video-frame/audio extraction — already installed in the provided
Dockerfile; install separately (`brew install ffmpeg` / `apt-get install ffmpeg`) for local runs.

## Deployment

**Not Vercel** — this app has an in-process APScheduler for the 3 cron jobs, shells out to `ffmpeg` for
video processing, and the agent's tool-calling loop can run several sequential OpenAI calls in one
request. None of that fits Vercel's stateless/serverless Python functions (no persistent background
scheduler, no `ffmpeg` in the runtime, and function timeouts). It needs a normal long-running host — the
existing `Dockerfile` runs as-is on any of them.

**Render** (`render.yaml` included, Docker-native):
1. New Web Service → connect this repo → Render detects `render.yaml` automatically.
2. Dashboard → Environment → fill in every var marked `sync: false` (tokens/keys) — same table as above.
3. Dashboard → Secret Files → add `google-service-account.json` with the service-account JSON content;
   Render mounts it at `/etc/secrets/google-service-account.json`, which is what `GOOGLE_SERVICE_ACCOUNT_FILE`
   in `render.yaml` already points at.
4. Deploy, then register `https://<your-render-url>/webhook/petpulse-core` with Meta (see below).

**Railway / Fly.io / a plain VM** — same `Dockerfile`, no `render.yaml` needed:
- Railway: "Deploy from repo", it auto-detects the Dockerfile; add env vars in its dashboard, and use a
  Railway **volume** (or a base64-encoded env var decoded on startup) for the Google credentials file.
- Fly.io: `fly launch` picks up the Dockerfile; use `fly secrets set` for the tokens/keys and `fly volumes`
  (or `fly secrets` decoded to a file at boot) for the Google credentials file.
- Plain VM: `docker build` + `docker run --env-file .env -v ./credentials:/app/credentials` exactly as in
  Setup above, behind whatever reverse proxy/TLS termination you're already using.

## Registering the webhook with Meta

Point Meta's WhatsApp webhook config at `https://<your-host>/webhook/petpulse-core`, verify token =
`WHATSAPP_VERIFY_TOKEN`. Meta calls `GET` once to verify, then `POST`s every inbound message/status
event to the same URL.

## Tests

```bash
pip install -r requirements.txt   # includes pytest/pytest-asyncio
pytest
```

Covers pure-logic pieces with no external dependency: pet-name resolution, phone normalization, the
doctor-slot generation algorithm, WhatsApp text chunking, webhook payload parsing, and the agent
tool-calling loop (OpenAI/Supabase/WhatsApp all mocked). Live WhatsApp/Supabase/Calendar/OpenAI
integration can't be exercised without real credentials — plug in the table above and test against a
real (or sandboxed) WhatsApp number.

## What's intentionally out of scope

Ported from the live n8n system's dead/unused surface (see the spec file linked above for detail):
the empty `clinics`/`vets`/`appointments`/`subscriptions`/`payments`/`knowledge_base`/`notifications`/
`audit_logs` tables, the orphaned `Send Pet Intake Flow`, the unpublished WhatsApp-Flow crypto endpoint,
and the single-shared-calendar limitation for vet scheduling (ported as-is, not fixed).
