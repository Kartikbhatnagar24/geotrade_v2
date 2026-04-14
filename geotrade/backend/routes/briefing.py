"""
backend/routes/briefing.py
───────────────────────────
GET /briefing/{country_iso}

Calls the Gemini API (gemini-1.5-flash) to generate a structured
geopolitical market briefing for a country, then caches the result
in the llm_briefings collection for BRIEFING_CACHE_HOURS (default 24h).

Requires: GEMINI_API_KEY in .env

Response shape:
  {
    iso, country,
    tension_snapshot: { score, label, date },
    analysis: {
      geopolitical_summary: str,
      market_impact:        str,
      affected_assets:      list[str],
      trade_ideas:          list[{ asset, direction, reasoning }],
      risk_level:           "high" | "medium" | "low",
      confidence_note:      str
    },
    created_at: ISO str,
    model:      str,
    from_cache: bool
  }
"""

import json
import re
from datetime import datetime, timezone

import google.generativeai as genai
from fastapi import APIRouter, HTTPException

from backend.core.database import get_db
from config.settings import settings

router = APIRouter(prefix="/briefing", tags=["Briefing"])

# ── Prompt template ───────────────────────────────────────────────────────────

_PROMPT = """\
You are a senior geopolitical risk analyst providing concise market intelligence.

Country         : {country} ({iso})
Tension Level   : {tension_label} ({tension_score_pct}/100)
Dominant Event  : {top_event_label}
Events Tracked  : {event_count}

Recent Headlines (last 7 days):
{headlines}

Based on this geopolitical data, produce a structured JSON analysis.
Return ONLY valid JSON — no markdown fences, no extra text.

{{
  "geopolitical_summary": "<2-3 sentences summarising the current situation>",
  "market_impact": "<1-2 sentences on the likely market impact>",
  "affected_assets": ["<asset class 1>", "<asset class 2>"],
  "trade_ideas": [
    {{"asset": "<TICKER or asset>", "direction": "<LONG or SHORT>", "reasoning": "<brief reason>"}}
  ],
  "risk_level": "<high or medium or low>",
  "confidence_note": "<one sentence on confidence and key uncertainties>"
}}
"""


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _is_fresh(doc: dict) -> bool:
    """True if the cached briefing is within BRIEFING_CACHE_HOURS."""
    raw = doc.get("created_at", "")
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - dt).total_seconds()
        return age_seconds < settings.BRIEFING_CACHE_HOURS * 3600
    except ValueError:
        return False


def _strip_json(raw: str) -> str:
    """Strip markdown code fences if Gemini wraps the JSON anyway."""
    raw = raw.strip()
    # Remove ```json ... ``` or ``` ... ```
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


# ── Route ─────────────────────────────────────────────────────────────────────

@router.get("/{country_iso}", summary="Gemini AI market briefing for a country")
def get_briefing(country_iso: str):
    """
    Generate (or return cached) a Gemini-powered geopolitical market briefing.

    - Checks llm_briefings cache first (24 h TTL).
    - On cache miss: fetches tension + recent headlines from MongoDB,
      calls Gemini 1.5 Flash, parses structured JSON, stores result.
    - Returns 503 if GEMINI_API_KEY is not configured.
    - Returns 404 if no tension data exists for the country.
    """
    iso = country_iso.upper()
    db  = get_db()

    # ── 1. Try cache ──────────────────────────────────────────
    cached = db[settings.COL_LLM_BRIEFINGS].find_one(
        {"iso": iso}, sort=[("created_at", -1)]
    )
    if cached and _is_fresh(cached):
        cached.pop("_id", None)
        cached["from_cache"] = True
        return cached

    # ── 2. Check API key ──────────────────────────────────────
    if not settings.GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY is not configured. Add it to .env to enable AI briefings.",
        )

    # ── 3. Fetch context from DB ──────────────────────────────
    tension_doc = db[settings.COL_DAILY_SIGNALS].find_one(
        {"iso": iso}, sort=[("date", -1)]
    )
    if not tension_doc:
        raise HTTPException(
            status_code=404,
            detail=f"No tension data for '{iso}'. Run pipeline steps 1-3 first.",
        )

    news_docs = list(
        db[settings.COL_PROCESSED_EVENTS]
        .find(
            {"countries.iso": iso},
            {"title": 1, "event_label": 1, "published_at": 1, "_id": 0},
        )
        .sort("published_at", -1)
        .limit(7)
    )
    if news_docs:
        headlines = "\n".join(
            f"- [{d.get('event_label', '?').upper()}] {d.get('title', '').strip()}"
            for d in news_docs
        )
    else:
        headlines = "- No recent headlines available in the database."

    # ── 4. Build prompt ───────────────────────────────────────
    prompt = _PROMPT.format(
        country          = tension_doc.get("country", iso),
        iso              = iso,
        tension_label    = tension_doc.get("tension_label", "medium").upper(),
        tension_score_pct= round(tension_doc.get("tension_score", 0.5) * 100),
        top_event_label  = tension_doc.get("top_event_label", "unknown"),
        event_count      = tension_doc.get("event_count", 0),
        headlines        = headlines,
    )

    # ── 5. Call Gemini ────────────────────────────────────────
    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model    = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        raw_text = response.text
    except Exception as exc:
        import traceback; traceback.print_exc()
        raise HTTPException(
            status_code=502,
            detail=f"Gemini API call failed: {exc}",
        )

    # ── 6. Parse JSON ─────────────────────────────────────────
    try:
        cleaned  = _strip_json(raw_text)
        analysis = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Gemini returned invalid JSON: {exc}. Raw: {raw_text[:300]}",
        )

    # ── 7. Build & cache document ─────────────────────────────
    doc = {
        "iso":     iso,
        "country": tension_doc.get("country", iso),
        "tension_snapshot": {
            "score": tension_doc.get("tension_score"),
            "label": tension_doc.get("tension_label"),
            "date":  tension_doc.get("date"),
        },
        "analysis":   analysis,
        "created_at": datetime.now(timezone.utc).isoformat() + "Z",
        "model":      "gemini-1.5-flash",
    }

    # Upsert — keep only the latest briefing per country
    db[settings.COL_LLM_BRIEFINGS].replace_one(
        {"iso": iso}, doc, upsert=True
    )

    doc["from_cache"] = False
    return doc
