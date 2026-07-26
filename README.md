# PetPulse Core Engine (FastAPI)

Python/FastAPI replacement for the n8n `PetPulse AI - Core Engine` workflow. WhatsApp is the entire
UI — one webhook receives every customer *and* vet message, and a single LLM agent (tool-calling loop)
decides what to do: save data, run triage, book a vet session, file a document, etc. See
`/Users/kes/.claude/plans/typed-coalescing-iverson.md` for the full architecture writeup.

## Setup

```bash
cp .env.example .env   # fill in the real values below
docker build -t petpulse-backend .
docker run -p 8000:8000 --env-file .env petpulse-backend
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
| `GOOGLE_CALENDAR_CLIENT_ID` / `GOOGLE_CALENDAR_CLIENT_SECRET` / `GOOGLE_CALENDAR_REFRESH_TOKEN` | Run `python scripts/get_google_refresh_token.py <client_id> <client_secret>` once, locally, with a browser — see the script's docstring for the one-time Google Cloud Console setup. **Not** a service account: confirmed live that a bare service account can't generate Google Meet links (`Invalid conference type value`) — Meet creation needs a real user-authenticated session or a Workspace account. Whichever Google account you log in as owns the calendar. |
| `GOOGLE_CALENDAR_ID` | The calendar to book into — `primary` (default) is that account's own default calendar; use a specific calendar ID if you want a different one |

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
2. Dashboard → Environment → fill in every var marked `sync: false` (tokens/keys) — same table as above,
   including the three `GOOGLE_CALENDAR_*` OAuth values from the script.
3. Deploy, then register `https://<your-render-url>/webhook/petpulse-core` with Meta (see below).

**Railway / Fly.io / a plain VM** — same `Dockerfile`, no `render.yaml` needed:
- Railway: "Deploy from repo", it auto-detects the Dockerfile; add all env vars (including the three
  `GOOGLE_CALENDAR_*` ones) in its dashboard.
- Fly.io: `fly launch` picks up the Dockerfile; `fly secrets set` for all tokens/keys.
- Plain VM: `docker build` + `docker run --env-file .env` exactly as in Setup above, behind whatever
  reverse proxy/TLS termination you're already using.

No credential *file* is needed for Google Calendar anymore (OAuth2 user credentials are plain env vars,
not a JSON key) — the `credentials/` volume mount above is only relevant if you still have other
file-based secrets there.

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
