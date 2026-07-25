"""Unifies `jCjl7XGrpW1K8kcO` (Find Available Slots / `request_doctor_session`,
spec §3.2) with the ~150-node `DocMsg -`/`CustResp -` action-switch chains
(spec §2) into explicit tools. In n8n these were reached via hardcoded
button-id classifiers that bypassed the LLM entirely; here the single agent
decides which of these to call — including for button taps, which arrive
as a plain-language system note rather than a routed action id (see
agent/orchestrator.py). Each tool still owns its own safety-critical
mechanics (slot double-booking recheck, calendar event creation) — the
agent decides *whether* to book, the tool guarantees *how*.

`doctor_sessions` state machine (unchanged from n8n):
  status: pending -> negotiating -> accepted | declined | cancelled -> completed
  awaiting_from: doctor_choice -> customer_time_input | doctor_time_input -> doctor_prescription (null once resolved)
  doctor_phone sentinel 'pending_doctor_choice' while no vet has been chosen yet.
"""

from datetime import datetime, timedelta
from typing import Any

from app.availability.slots import IST, compute_doctor_slots
from app.deps import AppContext
from app.ingestion.context import AgentContext
from app.integrations import google_calendar
from app.utils.pet_resolution import AMBIGUOUS_PET, resolve_pet

MAX_DOCTORS_LISTED = 9
SESSION_DURATION_MINUTES = 30


def _get_session(client, session_id: str) -> dict[str, Any] | None:
    resp = client.table("doctor_sessions").select("*").eq("id", session_id).limit(1).execute()
    return resp.data[0] if resp.data else None


def _get_profile(client, profile_id: str) -> dict[str, Any] | None:
    resp = client.table("profiles").select("*").eq("id", profile_id).limit(1).execute()
    return resp.data[0] if resp.data else None


def _get_pet(client, pet_id: str) -> dict[str, Any] | None:
    if not pet_id:
        return None
    resp = client.table("pets").select("*").eq("id", pet_id).limit(1).execute()
    return resp.data[0] if resp.data else None


async def request_doctor_session(
    ctx: AppContext,
    agent_ctx: AgentContext,
    pet_id: str = "",
    pet_name: str = "",
    case_summary: str = "",
    preferred_time: str = "",
) -> dict[str, Any]:
    if pet_id == AMBIGUOUS_PET:
        names = ", ".join(p.get("name", "?") for p in agent_ctx.pets)
        return {"success": False, "error": "ambiguous_pet", "message": f"Which pet is this for? On file: {names}"}

    client = ctx.supabase
    profile_id = agent_ctx.profile["id"]

    existing = (
        client.table("doctor_sessions")
        .select("*")
        .eq("profile_id", profile_id)
        .eq("doctor_phone", "pending_doctor_choice")
        .eq("status", "pending")
        .limit(1)
        .execute()
        .data
    )
    if existing:
        return {"success": True, "mode": "reminded_existing_list", "message": "You already have a vet list open — please pick a vet from it, or say 'cancel' to start over."}

    doctors = client.table("profiles").select("*").eq("role", "vet").limit(MAX_DOCTORS_LISTED).execute().data or []
    if not doctors:
        return {"success": False, "error": "no_doctors_available", "message": "No vets are available to book right now."}

    session_row = (
        client.table("doctor_sessions")
        .insert(
            {
                "profile_id": profile_id,
                "pet_id": pet_id or None,
                "doctor_phone": "pending_doctor_choice",
                "status": "pending",
                "awaiting_from": "doctor_choice",
                "case_summary": case_summary,
                "preferred_time": preferred_time or None,
            }
        )
        .execute()
        .data[0]
    )

    rows = [
        {
            "id": f"choose_doctor|{session_row['id']}|{doc['phone_number']}",
            "title": (doc.get("full_name") or "Vet")[:24],
            "description": f"{doc.get('experience_years', '?')}y exp • {doc.get('specialization', 'General')}"[:72],
        }
        for doc in doctors
    ]
    rows.append({"id": f"cancel_booking|{session_row['id']}", "title": "Cancel", "description": "Don't book right now"})

    await ctx.whatsapp.send_interactive_list(
        agent_ctx.profile["phone_number"],
        header="Choose a Vet",
        body="Here are our available vets. Pick one to see their open slots:",
        button_label="View Vets",
        sections=[{"title": "Available Vets", "rows": rows}],
    )

    return {"success": True, "mode": "doctor_catalogue_sent", "session_id": session_row["id"]}


async def select_doctor(ctx: AppContext, agent_ctx: AgentContext, session_id: str, doctor_phone: str) -> dict[str, Any]:
    client = ctx.supabase
    session = _get_session(client, session_id)
    if not session:
        return {"success": False, "error": "session_not_found"}

    client.table("doctor_sessions").update(
        {"doctor_phone": doctor_phone, "awaiting_from": "customer_time_input"}
    ).eq("id", session_id).execute()

    slots = await compute_doctor_slots(ctx.settings)
    if not slots:
        return {"success": True, "mode": "no_slots", "message": "That vet has no open slots in the next few days. Would you like to try another vet?"}

    by_day: dict[str, list] = {}
    for slot in slots:
        day_key = slot.start.strftime("%A, %d %b")
        by_day.setdefault(day_key, []).append(slot)

    sections = [
        {
            "title": day,
            "rows": [
                {"id": f"book_slot|{session_id}|{doctor_phone}|{s.to_iso()}", "title": s.label(), "description": ""}
                for s in day_slots
            ],
        }
        for day, day_slots in by_day.items()
    ]
    sections.append({"title": "Other", "rows": [{"id": f"cancel_booking|{session_id}", "title": "Cancel", "description": "Don't book right now"}]})

    await ctx.whatsapp.send_interactive_list(
        agent_ctx.profile["phone_number"],
        header="Choose a Time",
        body="Here are the next available slots with this vet:",
        button_label="View Slots",
        sections=sections,
    )
    return {"success": True, "mode": "slot_list_sent", "session_id": session_id}


async def book_slot(ctx: AppContext, agent_ctx: AgentContext, session_id: str, slot_start: str, doctor_phone: str = "") -> dict[str, Any]:
    client = ctx.supabase
    session = _get_session(client, session_id)
    if not session:
        return {"success": False, "error": "session_not_found"}
    doctor_phone = doctor_phone or session.get("doctor_phone")

    start = datetime.fromisoformat(slot_start)
    if start.tzinfo is None:
        start = start.replace(tzinfo=IST)
    end = start + timedelta(minutes=SESSION_DURATION_MINUTES)

    fresh_slots = await compute_doctor_slots(ctx.settings)
    if not any(s.start == start for s in fresh_slots):
        return await select_doctor(ctx, agent_ctx, session_id, doctor_phone)  # slot taken, resend fresh list

    return await _finalize_booking(ctx, session, doctor_phone, start, end)


async def _finalize_booking(ctx: AppContext, session: dict[str, Any], doctor_phone: str, start: datetime, end: datetime) -> dict[str, Any]:
    client = ctx.supabase
    customer_profile = _get_profile(client, session["profile_id"])
    pet = _get_pet(client, session.get("pet_id"))
    doctor_profile = client.table("profiles").select("*").eq("phone_number", doctor_phone).limit(1).execute().data
    doctor_name = doctor_profile[0].get("full_name", "your vet") if doctor_profile else "your vet"
    customer_name = customer_profile.get("full_name", "the pet owner") if customer_profile else "the pet owner"
    pet_name = pet.get("name", "the pet") if pet else "the pet"

    event = google_calendar.create_event_with_meet(
        ctx.settings,
        summary=f"PetPulse consult: {customer_name} & {doctor_name} ({pet_name})",
        description=session.get("case_summary", ""),
        start=start,
        end=end,
    )
    meet_link = google_calendar.extract_meet_link(event)

    client.table("doctor_sessions").update(
        {
            "status": "accepted",
            "awaiting_from": None,
            "doctor_phone": doctor_phone,
            "preferred_time": start.isoformat(),
            "meet_link": meet_link,
        }
    ).eq("id", session["id"]).execute()

    when_text = start.strftime("%a %d %b, %I:%M %p IST")
    if customer_profile:
        await ctx.whatsapp.send_text(
            customer_profile["phone_number"],
            f"Your session with {doctor_name} for {pet_name} is confirmed for {when_text}."
            + (f"\nJoin here: {meet_link}" if meet_link else ""),
        )
    await ctx.whatsapp.send_text(
        doctor_phone,
        f"New session confirmed with {customer_name} for {pet_name} at {when_text}."
        + (f"\nJoin here: {meet_link}" if meet_link else ""),
    )

    return {"success": True, "mode": "booked", "session_id": session["id"], "when": when_text, "meet_link": meet_link}


async def propose_time(
    ctx: AppContext, agent_ctx: AgentContext, session_id: str, proposed_time: str, proposed_by: str
) -> dict[str, Any]:
    client = ctx.supabase
    session = _get_session(client, session_id)
    if not session:
        return {"success": False, "error": "session_not_found"}

    awaiting_from = "doctor_time_input" if proposed_by == "customer" else "customer_time_input"
    client.table("doctor_sessions").update(
        {"status": "negotiating", "awaiting_from": awaiting_from, "preferred_time": proposed_time}
    ).eq("id", session_id).execute()

    start = datetime.fromisoformat(proposed_time)
    when_text = start.strftime("%a %d %b, %I:%M %p IST")

    customer_profile = _get_profile(client, session["profile_id"])
    recipient = session["doctor_phone"] if proposed_by == "customer" else (customer_profile["phone_number"] if customer_profile else None)
    if not recipient:
        return {"success": False, "error": "recipient_unknown"}

    await ctx.whatsapp.send_interactive_buttons(
        recipient,
        f"Proposed time: {when_text}. Does this work?",
        [
            {"id": f"accept_session:{session_id}", "title": "Accept"},
            {"id": f"decline_session:{session_id}", "title": "Decline"},
            {"id": f"retime_session:{session_id}", "title": "Suggest a time"},
        ],
    )
    return {"success": True, "mode": "proposal_sent", "session_id": session_id, "when": when_text}


async def respond_to_time_proposal(ctx: AppContext, agent_ctx: AgentContext, session_id: str, decision: str) -> dict[str, Any]:
    client = ctx.supabase
    session = _get_session(client, session_id)
    if not session:
        return {"success": False, "error": "session_not_found"}

    if decision == "accept":
        if not session.get("preferred_time"):
            return {"success": False, "error": "no_proposed_time"}
        start = datetime.fromisoformat(session["preferred_time"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=IST)
        end = start + timedelta(minutes=SESSION_DURATION_MINUTES)
        return await _finalize_booking(ctx, session, session["doctor_phone"], start, end)

    if decision == "decline":
        return await decline_session(ctx, agent_ctx, session_id)

    return {"success": True, "mode": "awaiting_retime", "message": "Ask them for a specific time, then call propose_time with it."}


async def accept_session(ctx: AppContext, agent_ctx: AgentContext, session_id: str) -> dict[str, Any]:
    return await respond_to_time_proposal(ctx, agent_ctx, session_id, "accept")


async def decline_session(ctx: AppContext, agent_ctx: AgentContext, session_id: str) -> dict[str, Any]:
    client = ctx.supabase
    session = _get_session(client, session_id)
    if not session:
        return {"success": False, "error": "session_not_found"}

    client.table("doctor_sessions").update({"status": "declined", "awaiting_from": None}).eq("id", session_id).execute()

    customer_profile = _get_profile(client, session["profile_id"])
    if customer_profile:
        await ctx.whatsapp.send_text(customer_profile["phone_number"], "Unfortunately that session request was declined. Would you like to pick another vet or time?")
    if session.get("doctor_phone") and session["doctor_phone"] != "pending_doctor_choice":
        await ctx.whatsapp.send_text(session["doctor_phone"], "You declined this session request.")

    return {"success": True, "mode": "declined", "session_id": session_id}


async def cancel_session(ctx: AppContext, agent_ctx: AgentContext, session_id: str) -> dict[str, Any]:
    client = ctx.supabase
    session = _get_session(client, session_id)
    if not session:
        return {"success": False, "error": "session_not_found"}

    client.table("doctor_sessions").update({"status": "cancelled", "awaiting_from": None}).eq("id", session_id).execute()

    customer_profile = _get_profile(client, session["profile_id"])
    other_party = session["doctor_phone"] if agent_ctx.role == "customer" else (customer_profile["phone_number"] if customer_profile else None)
    if other_party and other_party != "pending_doctor_choice":
        await ctx.whatsapp.send_text(other_party, "This session has been cancelled.")

    return {"success": True, "mode": "cancelled", "session_id": session_id}


async def mark_session_done(ctx: AppContext, agent_ctx: AgentContext, session_id: str) -> dict[str, Any]:
    client = ctx.supabase
    session = _get_session(client, session_id)
    if not session:
        return {"success": False, "error": "session_not_found"}

    client.table("doctor_sessions").update({"status": "completed", "awaiting_from": "doctor_prescription"}).eq("id", session_id).execute()
    return {"success": True, "mode": "session_completed", "instruction_to_llm": "Ask the vet for the prescription/treatment notes, then call file_prescription."}


async def file_prescription(
    ctx: AppContext, agent_ctx: AgentContext, session_id: str, medications: str, treatment_plan: str = ""
) -> dict[str, Any]:
    client = ctx.supabase
    session = _get_session(client, session_id)
    if not session:
        return {"success": False, "error": "session_not_found"}

    client.table("medical_records").insert(
        {
            "pet_id": session.get("pet_id"),
            "profile_id": session["profile_id"],
            "visit_date": datetime.now(tz=IST).date().isoformat(),
            "chief_complaint": session.get("case_summary"),
            "medications": medications,
            "treatment_plan": treatment_plan,
            "created_by": "vet",
        }
    ).execute()

    client.table("doctor_sessions").update({"awaiting_from": None}).eq("id", session_id).execute()

    customer_profile = _get_profile(client, session["profile_id"])
    if customer_profile:
        await ctx.whatsapp.send_text(
            customer_profile["phone_number"],
            f"Your vet has sent the prescription/notes from your session:\n\n{medications}"
            + (f"\n\nTreatment plan: {treatment_plan}" if treatment_plan else ""),
        )

    return {"success": True, "mode": "prescription_filed", "session_id": session_id}


async def list_my_appointments(ctx: AppContext, agent_ctx: AgentContext) -> dict[str, Any]:
    client = ctx.supabase
    phone = agent_ctx.profile["phone_number"]
    now_iso = datetime.now(tz=IST).isoformat()
    rows = (
        client.table("doctor_sessions")
        .select("id, status, preferred_time, meet_link, case_summary, profile_id, pet_id")
        .eq("doctor_phone", phone)
        .eq("status", "accepted")
        .gte("preferred_time", now_iso)
        .order("preferred_time")
        .limit(20)
        .execute()
        .data
        or []
    )

    appointments = []
    for row in rows:
        customer = _get_profile(client, row["profile_id"])
        pet = _get_pet(client, row.get("pet_id"))
        appointments.append(
            {
                "session_id": row["id"],
                "when": row["preferred_time"],
                "customer_name": customer.get("full_name") if customer else "Unknown",
                "pet_name": pet.get("name") if pet else "Unknown",
                "case_summary": row.get("case_summary"),
                "meet_link": row.get("meet_link"),
            }
        )

    return {"success": True, "count": len(appointments), "appointments": appointments}


async def relay_to_customer(ctx: AppContext, agent_ctx: AgentContext, session_id: str, message: str) -> dict[str, Any]:
    client = ctx.supabase
    session = _get_session(client, session_id)
    if not session:
        return {"success": False, "error": "session_not_found"}

    customer_profile = _get_profile(client, session["profile_id"])
    if not customer_profile:
        return {"success": False, "error": "customer_not_found"}

    await ctx.whatsapp.send_text(customer_profile["phone_number"], message)
    return {"success": True, "mode": "relayed", "session_id": session_id}
