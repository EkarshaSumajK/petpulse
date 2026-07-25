"""Shared client container, built once in the FastAPI lifespan and threaded
through ingestion/agent/tools instead of re-instantiating clients per
request."""

from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI
from supabase import Client

from app.config import Settings
from app.integrations.whatsapp import WhatsAppClient


@dataclass
class AppContext:
    settings: Settings
    http: httpx.AsyncClient
    whatsapp: WhatsAppClient
    supabase: Client
    openai: AsyncOpenAI
