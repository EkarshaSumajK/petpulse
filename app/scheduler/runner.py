"""Wires the 3 cron jobs into an in-process APScheduler, started/stopped
from the FastAPI lifespan (spec §9 schedules: reminders/followups daily at
10:00 IST, retention weekly Sunday 3am IST)."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.deps import AppContext
from app.scheduler.jobs import retain_chat_history, send_new_parent_followups, send_vaccination_reminders


def start_scheduler(ctx: AppContext) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=ctx.settings.timezone)

    scheduler.add_job(send_vaccination_reminders, CronTrigger(hour=10, minute=0), args=[ctx], id="vaccination_reminders")
    scheduler.add_job(send_new_parent_followups, CronTrigger(hour=10, minute=0), args=[ctx], id="new_parent_followups")
    scheduler.add_job(retain_chat_history, CronTrigger(day_of_week="sun", hour=3, minute=0), args=[ctx], id="chat_history_retention")

    scheduler.start()
    return scheduler
