"""Work resolution service — resolves calendar work based on subsequent meeting evidence.

Detects when decisions, updates, or statements in a meeting resolve, complete,
or cancel previously scheduled calendar events, providing clear reasoning and evidence.
"""

import re
from difflib import SequenceMatcher
from typing import Optional


# Keywords and patterns signaling that a previous task or issue has been resolved or completed
_COMPLETION_PATTERNS = [
    r'\b(?:has\s+been|was|is|we\s+have|already|finally)\s+(?:completed|finished|resolved|done|delivered|fixed|closed|shipped|merged)\b',
    r'\b(?:finished|completed|resolved|solved|fixed)\s+(?:the|this|that|our)\b',
    r'\b(?:signed\s+off|got\s+the\s+sign-off|approved|signed|cleared)\b',
    r'\bno\s+longer\s+(?:needed|necessary|required|blocked|an\s+issue|a\s+problem)\b',
    r'\b(?:cancelled|dropped|called\s+off|scrapped|abandoned)\b',
    r'\b(?:resolved\s+the|fixed\s+the|addressed\s+the)\s+(\w+)\b',
]

_COMPLETION_RE = re.compile('|'.join(_COMPLETION_PATTERNS), re.IGNORECASE)


def _normalize_tokens(text: str) -> set[str]:
    """Extract significant lowercase tokens (length >= 3) excluding stop words."""
    stop_words = {
        "the", "and", "for", "with", "that", "this", "from", "will", "shall",
        "must", "should", "can", "our", "your", "their", "are", "was", "were",
        "been", "have", "has", "had", "item", "task", "action", "meeting"
    }
    tokens = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    return {t for t in tokens if t not in stop_words}


def _similarity(a: str, b: str) -> float:
    """Calculate token Jaccard similarity and sequence matcher ratio."""
    ta = _normalize_tokens(a)
    tb = _normalize_tokens(b)
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)
    seq = SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return max(jaccard, seq)


def detect_work_resolutions(
    active_events: list[dict],
    meeting_title: str,
    decisions: list[dict],
    transcript: str,
    raw_action_items: Optional[list[dict]] = None
) -> list[dict]:
    """Scan new meeting data to find existing calendar events that are resolved.

    Returns a list of dicts:
    [
        {
            "event_id": int,
            "title": str,
            "status": "RESOLVED" | "CANCELLED",
            "reason": str,
            "evidence": str
        }
    ]
    """
    resolutions = []
    lines = [line.strip() for line in transcript.splitlines() if line.strip()]

    # Collect statements from decisions and completed utterances
    resolution_candidates = []

    # 1. Inspect decisions
    for d in decisions:
        text = d.get("decision") or d.get("text") or ""
        context = d.get("context") or ""
        if text:
            resolution_candidates.append({
                "type": "decision",
                "text": text,
                "evidence": f"Decision: {text}" + (f" (Context: {context})" if context else "")
            })

    # 2. Inspect transcript lines that contain completion or resolution phrases
    for line in lines:
        if _COMPLETION_RE.search(line):
            resolution_candidates.append({
                "type": "utterance",
                "text": line,
                "evidence": line
            })

    for event in active_events:
        event_id = event.get("id")
        event_title = event.get("title", "")
        event_desc = event.get("description", "")
        event_owner = (event.get("owner") or "").lower()

        # Check against all resolution candidates
        for cand in resolution_candidates:
            cand_text = cand["text"]
            cand_lower = cand_text.lower()

            # Check overlap between event title/description and candidate text
            title_sim = _similarity(event_title, cand_text)
            desc_sim = _similarity(event_desc, cand_text) if event_desc else 0.0

            # Direct keyword matching: check if significant nouns of event appear in completion statement
            title_tokens = _normalize_tokens(event_title)
            shared_tokens = title_tokens & _normalize_tokens(cand_text)
            token_match = len(shared_tokens) >= 2 or (len(title_tokens) == 1 and len(shared_tokens) == 1)

            is_match = title_sim >= 0.40 or desc_sim >= 0.45 or (token_match and _COMPLETION_RE.search(cand_text))

            if is_match:
                # Determine if cancelled or resolved
                is_cancelled = bool(re.search(r'\b(?:cancelled|dropped|called\s+off|scrapped|no\s+longer\s+needed)\b', cand_lower))
                new_status = "CANCELLED" if is_cancelled else "RESOLVED"

                reason = (
                    f"Resolved in meeting '{meeting_title}' based on statement: '{cand_text}'. "
                    f"Identified evidence: {cand['evidence']}"
                )

                resolutions.append({
                    "event_id": event_id,
                    "title": event_title,
                    "status": new_status,
                    "reason": reason,
                    "evidence": cand["evidence"]
                })
                break  # Matched this event, proceed to next

    return resolutions
