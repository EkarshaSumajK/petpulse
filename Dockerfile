FROM python:3.12-slim

# Force stdout/stderr unbuffered so logs (and crash tracebacks) show up
# immediately in PaaS log viewers instead of sitting in a pipe buffer.
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# Fixed port 8000 — this is what the currently-live Railway deploy's networking
# is already pointed at. Do not switch back to a shell-expanded ${PORT} here
# without also updating Railway's Settings > Networking target port to match,
# or the proxy and the app end up listening on two different ports (silent
# "connection refused" even though the container is healthy).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
