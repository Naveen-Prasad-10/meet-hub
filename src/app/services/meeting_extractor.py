"""Meeting Extraction Service — enterprise-grade transcript-to-JSON extraction.

Accepts a raw transcript and returns a single JSON object matching the
enterprise meeting-extraction schema:

    {
        "meeting_title": "...",
        "summary": "...",
        "decisions": [{"decision": "...", "evidence": "..."}],
        "tasks": [{"title": "...", "description": "...", "assignee": "...|null",
                    "due_date": "YYYY-MM-DD|null", "evidence": "..."}],
        "blockers": [{"issue": "...", "evidence": "..."}]
    }

Design decisions
----------------
- Reuses the battle-tested transcript_processor (clean, speakers, decisions,
  action_items) and intelligence_extractor (priority / confidence / dedup)
  pipelines rather than duplicating logic.
- Blocker / risk extraction is new — regex-based with speaker attribution.
- Title generation is extractive (top decision or topic), not generative.
- Evidence is the original transcript line(s), not the normalised text.
"""

import re
from typing import Optional

from app.services.transcript_processor import (
    clean_transcript,
    detect_speakers,
    extract_meeting_date,
    extract_decisions,
    extract_action_items,
)
from app.services.intelligence_extractor import (
    extract_intelligence,
    _normalize_text,
)


# ---------------------------------------------------------------------------
# Blocker / risk / dependency / open-question extraction
# ---------------------------------------------------------------------------

_BLOCKER_PATTERNS = [
    # Explicit blocker / blocked
    (
        r"(?:^|\b)(?:blocker|blocked\s+(?:by|on)|blocking)\s*[:\-]?\s*([^.\n!?]+)",
        "blocker",
    ),
    # Risk statements
    (
        r"(?:^|\b)(?:risk|at\s+risk|risky)\s*[:\-]?\s*([^.\n!?]+)",
        "risk",
    ),
    # Dependency statements
    (
        r"(?:^|\b)(?:depend(?:s|ent|ency|ing)\s+on|waiting\s+(?:on|for)|"
        r"need(?:s)?\s+(?:from|input\s+from|approval\s+from|sign-?off\s+from))\s*"
        r"[:\-]?\s*([^.\n!?]+)",
        "dependency",
    ),
    # Open questions / unknowns
    (
        r"(?:^|\b)(?:open\s+question|unknown|unclear|undecided|unresolved|"
        r"still\s+need\s+to\s+(?:figure\s+out|decide|determine|clarify))\s*"
        r"[:\-]?\s*([^.\n!?]+)",
        "open_question",
    ),
    # Constraints
    (
        r"(?:^|\b)(?:constraint|limitation|bottleneck|capacity\s+issue|"
        r"resource\s+constraint|bandwidth\s+(?:issue|concern|problem))\s*"
        r"[:\-]?\s*([^.\n!?]+)",
        "constraint",
    ),
    # Concern phrasing ("I'm concerned about …", "concern is …")
    (
        r"(?:^|\b)(?:concern(?:ed)?|worried)\s+(?:about|that|is)\s*[:\-]?\s*"
        r"([^.\n!?]+)",
        "risk",
    ),
    # "We can't … until …" pattern
    (
        r"(?:^|\b)(?:can'?t|cannot|unable\s+to)\s+([^.\n!?]*?\buntil\b[^.\n!?]+)",
        "blocker",
    ),
]
_BLOCKER_RES = [
    (re.compile(pat, re.IGNORECASE | re.MULTILINE), label)
    for pat, label in _BLOCKER_PATTERNS
]


def _extract_blockers(clean_text: str) -> list[dict]:
    """Extract blockers, risks, dependencies, and open questions.

    Returns a deduplicated list of dicts:
        {"issue": "…", "evidence": "original line"}
    """
    blockers: list[dict] = []
    seen: set[str] = set()
    lines = clean_text.split("\n")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        for regex, _label in _BLOCKER_RES:
            match = regex.search(stripped)
            if match:
                issue_text = match.group(1).strip() if match.lastindex else match.group(0).strip()
                issue_text = _normalize_text(issue_text)
                # Avoid near-empty or duplicate entries
                if len(issue_text) < 8:
                    continue
                key = issue_text.lower()
                if key not in seen:
                    seen.add(key)
                    blockers.append({
                        "issue": issue_text,
                        "evidence": stripped,
                    })
                break  # one match per line is enough

    return blockers


# ---------------------------------------------------------------------------
# Title generation (extractive, not generative)
# ---------------------------------------------------------------------------

def _generate_title(
    decisions: list[dict],
    action_items: list[dict],
    speakers: list[str],
    meeting_date: Optional[str],
) -> str:
    """Generate a short meeting title from extracted content.

    Strategy (priority order):
    1. First HIGH-priority decision, trimmed to ~60 chars.
    2. First action-item task description.
    3. Fallback to "Team Meeting — <date>".
    """
    # Try the first decision
    if decisions:
        text = decisions[0].get("text", decisions[0].get("decision", ""))
        title = _truncate(text, 60)
        if title:
            return title

    # Try the first action item
    if action_items:
        task = action_items[0].get("task", action_items[0].get("what", ""))
        title = _truncate(task, 60)
        if title:
            return title

    # Fallback
    date_part = f" — {meeting_date}" if meeting_date else ""
    speaker_part = f" ({', '.join(speakers[:3])})" if speakers and speakers != ["Unknown"] else ""
    return f"Team Meeting{speaker_part}{date_part}"


def _truncate(text: str, max_len: int) -> str:
    """Truncate to max_len at a word boundary, appending '…' if needed."""
    text = text.strip().rstrip(".")
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    truncated = text[:max_len].rsplit(" ", 1)[0]
    return truncated.rstrip(".,;:—-") + "…"


# ---------------------------------------------------------------------------
# Summary generation (extractive)
# ---------------------------------------------------------------------------

def _generate_summary(
    decisions: list[dict],
    action_items: list[dict],
    blockers: list[dict],
    speakers: list[str],
) -> str:
    """Generate a 2-3 sentence executive summary from extracted data."""
    parts: list[str] = []

    # Sentence 1: meeting composition
    n_speakers = len([s for s in speakers if s not in ("Unknown", "Unassigned")])
    if n_speakers:
        parts.append(
            f"Meeting with {n_speakers} participant{'s' if n_speakers != 1 else ''} "
            f"({', '.join(speakers[:4])})."
        )

    # Sentence 2: decisions + actions
    n_dec = len(decisions)
    n_act = len(action_items)
    segments: list[str] = []
    if n_dec:
        segments.append(f"{n_dec} decision{'s' if n_dec != 1 else ''}")
    if n_act:
        segments.append(f"{n_act} action item{'s' if n_act != 1 else ''}")
    if segments:
        parts.append(f"Produced {' and '.join(segments)}.")

    # Sentence 3: blockers
    n_blk = len(blockers)
    if n_blk:
        parts.append(
            f"{n_blk} risk{'s' if n_blk != 1 else ''}/blocker{'s' if n_blk != 1 else ''} "
            f"identified."
        )

    return " ".join(parts) if parts else "No actionable information extracted from this meeting."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_meeting_info(raw_transcript: str) -> dict:
    """Full extraction pipeline → enterprise JSON schema.

    Steps:
        1. Clean transcript, detect speakers, extract date.
        2. Extract raw decisions + action items (transcript_processor).
        3. Score / dedup via intelligence_extractor.
        4. Extract blockers / risks / dependencies.
        5. Generate title + summary.
        6. Reshape into the required output schema with evidence.

    Returns
    -------
    dict matching the enterprise meeting-extraction JSON schema.
    """
    # ── Step 1: pre-process ────────────────────────────────────────────────
    clean_text = clean_transcript(raw_transcript)
    speakers = detect_speakers(clean_text)
    meeting_date = extract_meeting_date(clean_text)

    # ── Step 2: raw extraction ─────────────────────────────────────────────
    raw_decisions = extract_decisions(clean_text)
    raw_actions = extract_action_items(clean_text, speakers, meeting_date)

    # ── Step 3: intelligence scoring + dedup ────────────────────────────────
    intel = extract_intelligence({
        "decisions": raw_decisions,
        "action_items": raw_actions,
    })
    scored_decisions = intel["decisions"]
    scored_actions = intel["action_items"]

    # ── Step 4: blockers ───────────────────────────────────────────────────
    blockers = _extract_blockers(clean_text)

    # ── Step 5: title + summary ────────────────────────────────────────────
    title = _generate_title(scored_decisions, scored_actions, speakers, meeting_date)
    summary = _generate_summary(scored_decisions, scored_actions, blockers, speakers)

    # ── Step 6: reshape to output schema ───────────────────────────────────
    #
    # Map decisions: the raw_decisions list carries the original context and
    # decision text; we use those for evidence.
    out_decisions: list[dict] = []
    for scored in scored_decisions:
        # Find the matching raw decision for evidence
        evidence = _find_evidence(scored["text"], raw_decisions, key="decision")
        out_decisions.append({
            "decision": scored["text"],
            "evidence": evidence,
        })

    # Map tasks: scored_actions have owner/task/deadline; raw_actions have
    # context lines.
    out_tasks: list[dict] = []
    for scored in scored_actions:
        evidence = _find_evidence(scored["task"], raw_actions, key="what")
        assignee: Optional[str] = scored.get("owner")
        if assignee in ("Unassigned", "Unknown", ""):
            assignee = None
        due_date: Optional[str] = scored.get("deadline")
        if due_date and "[UNRESOLVED]" in due_date:
            due_date = None  # schema rule: don't invent dates
        out_tasks.append({
            "title": _truncate(scored["task"], 80),
            "description": scored["task"],
            "assignee": assignee,
            "due_date": due_date,
            "evidence": evidence,
        })

    return {
        "meeting_title": title,
        "summary": summary,
        "decisions": out_decisions,
        "tasks": out_tasks,
        "blockers": blockers,
    }


def _find_evidence(
    normalised_text: str,
    raw_items: list[dict],
    key: str,
) -> Optional[str]:
    """Find the best matching raw item and return its context as evidence."""
    norm_lower = normalised_text.lower().rstrip(".")
    best_ctx: Optional[str] = None
    best_score = 0.0

    for item in raw_items:
        raw_text = (item.get(key) or "").lower().rstrip(".")
        # Quick substring check
        if norm_lower in raw_text or raw_text in norm_lower:
            return item.get("context") or raw_text
        # Fuzzy fallback
        from difflib import SequenceMatcher
        score = SequenceMatcher(None, norm_lower, raw_text).ratio()
        if score > best_score:
            best_score = score
            best_ctx = item.get("context") or raw_text

    return best_ctx if best_score > 0.5 else None
