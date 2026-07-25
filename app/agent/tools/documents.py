"""Ports `HndYcT5EWackv3ul` — Pet Document Locker (`send_pet_document` /
`get_pet_passport`, spec §3.6) plus the new `file_document` tool, which
replaces n8n's always-on silent `Classify & Route Document` ->
`Should File Document?` -> insert pipeline (spec §2) with an explicit,
agent-invoked action — the one deliberate behavior shift called out in the
plan."""

import json
from datetime import date
from typing import Any

from app.deps import AppContext
from app.ingestion.context import AgentContext
from app.integrations.openai_client import json_completion
from app.integrations.supabase_client import sign_storage_url, upload_to_storage
from app.media_pipeline.classify import LABEL_TO_KEY, VALID_DOCUMENT_TYPES
from app.utils.pet_resolution import resolve_pet

VACCINATION_ROUTE_MAP = {
    "subcutaneous": "Subcutaneous", "sc": "Subcutaneous", "sq": "Subcutaneous",
    "intramuscular": "Intramuscular", "im": "Intramuscular",
    "oral": "Oral", "po": "Oral",
    "intranasal": "Intranasal", "in": "Intranasal",
}

MEDREC_EXTRACT_SYSTEM_PROMPT = """Extract structured medical data from a vet document analysis. Respond with \
strict JSON:
{"record_kind": "vaccination"|"clinical"|"none", "visit_date": "YYYY-MM-DD" or null, \
"chief_complaint": string or null, "diagnosis": string or null, "treatment_plan": string or null, \
"medications": string or null, \
"vaccinations": [{"vaccine_name": string, "manufacturer": string or null, "batch_number": string or null, \
"date_administered": "YYYY-MM-DD", "next_due_date": "YYYY-MM-DD" or null, \
"next_due_source": "document"|"inferred", "route": string or null}]}
If next_due_date isn't stated, infer it from standard intervals (puppy/kitten: 3-4 weeks; adult booster: 1 year) \
and mark next_due_source="inferred". Omit vaccination rows missing vaccine_name or date_administered."""


async def send_pet_document(
    ctx: AppContext, agent_ctx: AgentContext, pet_id: str = "", pet_name: str = "", document_type: str = ""
) -> dict[str, Any]:
    resolution = resolve_pet(agent_ctx.pets, pet_id=pet_id, pet_name=pet_name, auto_resolve_single=True)
    if resolution.ambiguous:
        return {"success": False, "error": "ambiguous_pet", "message": "Which pet's documents?"}
    if not resolution.pet:
        return {"success": False, "error": "no_pet_on_file"}

    query = ctx.supabase.table("documents").select("*").eq("pet_id", resolution.pet["id"])
    if document_type:
        query = query.ilike("document_type", f"%{document_type}%")
    docs = query.order("uploaded_at", desc=True).limit(3).execute().data or []

    if not docs:
        return {"success": True, "mode": "no_documents", "message": "No matching documents on file for this pet."}

    phone = agent_ctx.profile["phone_number"]
    for doc in docs:
        bucket, _, object_path = doc["storage_path"].partition("/")
        signed_url = sign_storage_url(ctx.supabase, bucket, object_path)
        caption = f"{doc['document_type']} for {resolution.pet['name']}"
        if (doc.get("mime_type") or "").startswith("image/"):
            await ctx.whatsapp.send_image(phone, signed_url, caption)
        else:
            await ctx.whatsapp.send_document(phone, signed_url, doc["document_name"], caption)

    return {
        "success": True,
        "mode": "documents_sent",
        "count": len(docs),
        "instruction_to_llm": "Documents were already sent as WhatsApp attachments. Confirm briefly — do NOT restate or summarise their contents.",
    }


async def get_pet_passport(ctx: AppContext, agent_ctx: AgentContext, pet_id: str = "", pet_name: str = "") -> dict[str, Any]:
    resolution = resolve_pet(agent_ctx.pets, pet_id=pet_id, pet_name=pet_name, auto_resolve_single=True)
    if resolution.ambiguous:
        return {"success": False, "error": "ambiguous_pet", "message": "Which pet's passport?"}
    pet = resolution.pet
    if not pet:
        return {"success": False, "error": "no_pet_on_file"}

    vaccinations = (
        ctx.supabase.table("vaccinations").select("*").eq("pet_id", pet["id"])
        .order("date_administered", desc=True).execute().data or []
    )
    medical_records = (
        ctx.supabase.table("medical_records").select("*").eq("pet_id", pet["id"])
        .order("visit_date", desc=True).limit(8).execute().data or []
    )

    today = date.today().isoformat()
    lines = [f"*{pet['name']}'s Pet Passport*", f"Species/Breed: {pet.get('species', '?')} / {pet.get('breed', '?')}"]
    if pet.get("age"):
        lines.append(f"Age: {pet['age']}")
    if pet.get("weight"):
        lines.append(f"Weight: {pet['weight']} {pet.get('weight_unit', 'kg')}")
    if pet.get("date_of_birth"):
        lines.append(f"DOB: {pet['date_of_birth']}")
    if pet.get("microchip_number"):
        lines.append(f"Microchip: {pet['microchip_number']}")

    overdue_count = 0
    lines.append("\n*Vaccinations:*")
    for vax in vaccinations:
        overdue = vax.get("next_due_date") and vax["next_due_date"] < today
        if overdue:
            overdue_count += 1
        flag = " (OVERDUE)" if overdue else ""
        lines.append(f"- {vax['vaccine_name']} — {vax['date_administered']}{flag}")

    lines.append("\n*Recent medical records:*")
    for rec in medical_records:
        summary = (rec.get("chief_complaint") or rec.get("diagnosis") or "visit")[:140]
        lines.append(f"- {rec['visit_date']}: {summary}")
    older = len(medical_records) - 8 if len(medical_records) > 8 else 0
    if older > 0:
        lines.append(f"...and {older} older")

    passport_text = "\n".join(lines)
    return {
        "success": True,
        "mode": "passport",
        "passport_text": passport_text,
        "overdue_vaccinations": overdue_count,
        "instruction_to_llm": "Relay passport_text verbatim, preserving line breaks. This is ground truth — never contradict it.",
    }


async def file_document(
    ctx: AppContext,
    agent_ctx: AgentContext,
    pet_name: str = "",
    document_type: str = "",
) -> dict[str, Any]:
    media = getattr(agent_ctx, "pending_media", None)
    if not media or not media.document_bytes:
        return {"success": False, "error": "no_pending_media", "message": "There's no document from this turn to file."}

    classification = media.document_classification
    resolved_type = document_type if document_type in VALID_DOCUMENT_TYPES else (
        classification.document_type if classification else "Other"
    )
    target_pet = None
    if pet_name:
        resolution = resolve_pet(agent_ctx.pets, pet_name=pet_name, auto_resolve_single=True)
        target_pet = resolution.pet
    if not target_pet and classification:
        target_pet = classification.target_pet
    if not target_pet:
        return {"success": False, "error": "ambiguous_pet", "message": "Which pet is this document for?"}

    bucket = classification.bucket if classification else "medical-documents"
    ext = (media.document_mime_type or "").split("/")[-1] or "bin"
    timestamp = int(date.today().strftime("%Y%m%d"))
    object_path = f"{target_pet['id']}/{timestamp}-{LABEL_TO_KEY.get(resolved_type, 'other')}.{ext}"
    storage_path = f"{bucket}/{object_path}"

    upload_to_storage(ctx.supabase, bucket, object_path, media.document_bytes, media.document_mime_type or "application/octet-stream")

    is_verified = classification.is_verified if classification else False
    doc_row = (
        ctx.supabase.table("documents")
        .insert(
            {
                "pet_id": target_pet["id"],
                "profile_id": agent_ctx.profile["id"],
                "document_name": f"{resolved_type} - {target_pet['name']}",
                "document_type": resolved_type,
                "storage_path": storage_path,
                "mime_type": media.document_mime_type,
                "ocr_text": media.media_context,
                "ai_summary": media.media_context[:400],
                "is_verified": is_verified,
            }
        )
        .execute()
    )

    medrec_result = await _extract_and_store_medical_record(ctx, agent_ctx, target_pet, media.media_context, is_verified)

    return {
        "success": True,
        "document_id": doc_row.data[0]["id"],
        "document_type": resolved_type,
        "pet_name": target_pet["name"],
        "is_verified": is_verified,
        "medical_record_extraction": medrec_result,
        "instruction_to_llm": "Document has been filed. You may now confirm it was saved/noted/on file — do not restate its contents unprompted.",
    }


async def _extract_and_store_medical_record(
    ctx: AppContext, agent_ctx: AgentContext, pet: dict[str, Any], analysis_text: str, is_verified: bool
) -> dict[str, Any]:
    try:
        raw = await json_completion(
            ctx.openai, ctx.settings, MEDREC_EXTRACT_SYSTEM_PROMPT, analysis_text, reasoning_effort="low"
        )
        extracted = json.loads(raw)
    except Exception:
        return {"record_kind": "none"}

    kind = extracted.get("record_kind", "none")
    disclaimer = "" if is_verified else " (not vet-verified"

    if kind == "vaccination":
        rows = []
        for vax in extracted.get("vaccinations", []):
            if not vax.get("vaccine_name") or not vax.get("date_administered"):
                continue
            route = VACCINATION_ROUTE_MAP.get((vax.get("route") or "").lower(), "Other")
            notes_parts = []
            if not is_verified:
                notes_parts.append("not vet-verified")
            if vax.get("next_due_source") == "inferred":
                notes_parts.append("next due date inferred, not from document")
            rows.append(
                {
                    "pet_id": pet["id"],
                    "profile_id": agent_ctx.profile["id"],
                    "vaccine_name": vax["vaccine_name"],
                    "manufacturer": vax.get("manufacturer"),
                    "batch_number": vax.get("batch_number"),
                    "date_administered": vax["date_administered"],
                    "next_due_date": vax.get("next_due_date"),
                    "route": route,
                    "notes": "; ".join(notes_parts) or None,
                }
            )
        if rows:
            ctx.supabase.table("vaccinations").insert(rows).execute()
        return {"record_kind": "vaccination", "rows_inserted": len(rows)}

    if kind == "clinical":
        ctx.supabase.table("medical_records").insert(
            {
                "pet_id": pet["id"],
                "profile_id": agent_ctx.profile["id"],
                "visit_date": extracted.get("visit_date") or date.today().isoformat(),
                "chief_complaint": extracted.get("chief_complaint"),
                "diagnosis": extracted.get("diagnosis"),
                "treatment_plan": extracted.get("treatment_plan"),
                "medications": extracted.get("medications"),
                "created_by": "ai",
            }
        ).execute()
        return {"record_kind": "clinical"}

    return {"record_kind": "none"}
