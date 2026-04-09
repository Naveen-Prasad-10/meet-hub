"""Meeting Intelligence Extractor — production-grade extraction service.

Extracts ONLY high-value, non-redundant, decision-critical information
from processed transcript data, returning strict JSON output with:
  - priority (HIGH / MEDIUM / LOW)
  - confidence (0.0–1.0)
  - deduplication
  - professional, normalized language

Fix log
-------
Bug 5  – _deduplicate: list mutation during iteration replaced with in-place
         index swap.
Bug 6  – _score_confidence: unbounded strong-signal accumulation capped at +0.15.
Bug 7  – extract_intelligence: .get() silent fallback replaced with schema
         validation + KeyError.
Bug H  – Negated HIGH keywords ("not urgent", "no longer blocked") no longer
         incorrectly score as HIGH.
Bug I  – Vague tasks ("fix the system", "sort it out") flagged with
         needs_clarification=True.
Bug J  – extract_intelligence now also accepts "owner"/"assigned_to" key aliases
         in addition to "who" (loophole #2 / upstream key rename).
Bug K  – _deduplicate threshold lowered to 0.70 and text normalised before
         comparison to catch same-task paraphrases (loophole #6).
"""

import re
from difflib import SequenceMatcher
from typing import Optional


# ---------------------------------------------------------------------------
# Priority keyword sets
# ---------------------------------------------------------------------------

_HIGH_KEYWORDS = {
    "deadline", "blocker", "blocked", "critical", "urgent", "asap",
    "immediately", "must", "eod", "cob", "eob", "today", "tomorrow",
    "by end of", "launch", "release", "outage", "incident", "escalate",
    "breaking", "hotfix", "p0", "p1", "showstopper",
}

_MEDIUM_KEYWORDS = {
    "should", "plan", "review", "follow up", "next sprint", "backlog",
    "schedule", "prepare", "draft", "investigate", "evaluate", "assess",
    "update", "revise", "improve", "optimize", "discuss",
}

_LOW_KEYWORDS = {
    "optional", "nice to have", "consider", "explore", "maybe",
    "sometime", "eventually", "low priority", "fyi", "informational",
    "brainstorm", "idea",
}

# Negation prefixes that cancel a following HIGH keyword
_NEGATION_PREFIX = re.compile(
    r'\b(?:not|no\s+longer|no|never|isn\'t|aren\'t|wasn\'t|weren\'t'
    r'|don\'t|doesn\'t|didn\'t|won\'t|wouldn\'t|hasn\'t|haven\'t)\b',
    re.IGNORECASE,
)

# Vague task phrases that indicate the item needs human clarification
_VAGUE_PATTERNS = [
    r'^fix\s+(it|this|that|the\s+\w+)\s*\.?$',
    r'^sort\s+(it|this|that)\s+out\s*\.?$',
    r'^handle\s+(it|this|that)\s*\.?$',
    r'^deal\s+with\s+(it|this|that)\s*\.?$',
    r'^look\s+into\s+it\s*\.?$',
    r'^take\s+care\s+of\s+it\s*\.?$',
    r'^check\s+(it|this)\s*\.?$',
    r'^\w{1,20}\s+the\s+system\s*\.?$',   # "fix the system", "update the system"
    r'^\w{1,20}\s+the\s+thing\s*\.?$',
]
_VAGUE_RE = re.compile('|'.join(_VAGUE_PATTERNS), re.IGNORECASE)


def _is_vague_task(text: str) -> bool:
    return bool(_VAGUE_RE.match(text.strip()))


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _normalize_text(text: str) -> str:
    """Normalize: collapse whitespace, remove fillers, sentence-case, trailing period."""
    text = re.sub(r"\s+", " ", text).strip()
    fillers = [
        r"\bum\b", r"\buh\b", r"\byou know\b", r"\blike\b(?=,|\s)",
        r"\bbasically\b", r"\bsort of\b", r"\bkind of\b",
        r"\bi mean\b", r"\bi think\b", r"\bi guess\b",
    ]
    for filler in fillers:
        text = re.sub(filler, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if text:
        text = text[0].upper() + text[1:]
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _score_priority(text: str, has_deadline: bool = False) -> str:
    """Determine priority with negation awareness.

    FIX (Bug H / loophole #9): keywords that appear after a negation ("not urgent",
    "no longer blocked") are skipped so they don't inflate priority.
    """
    if has_deadline:
        return "HIGH"

    lower = text.lower()

    # Build a set of word positions that are negated
    negated_spans: list[tuple[int, int]] = []
    for neg_match in _NEGATION_PREFIX.finditer(lower):
        # Treat up to 30 chars after the negation as negated territory
        negated_spans.append((neg_match.start(), neg_match.end() + 30))

    def _is_negated(pos: int) -> bool:
        return any(start <= pos <= end for start, end in negated_spans)

    for kw in _HIGH_KEYWORDS:
        idx = lower.find(kw)
        if idx != -1 and not _is_negated(idx):
            return "HIGH"

    for kw in _MEDIUM_KEYWORDS:
        if kw in lower:
            return "MEDIUM"

    for kw in _LOW_KEYWORDS:
        if kw in lower:
            return "LOW"

    return "MEDIUM"


def _score_confidence(text: str, context: Optional[str] = None) -> float:
    """Score confidence (0–1).

    FIX (Bug 6): total boost from strong signals capped at +0.15.
    """
    lower = text.lower()
    score = 0.7

    strong_signals = [
        "decided", "agreed", "approved", "confirmed", "finalized",
        "will", "shall", "must", "committed", "resolved",
    ]
    boost = sum(0.08 for sig in strong_signals if sig in lower)
    score += min(boost, 0.15)

    weak_signals = [
        "maybe", "possibly", "might", "could", "consider",
        "think", "suggest", "perhaps", "tentative", "tbd",
    ]
    for sig in weak_signals:
        if sig in lower:
            score -= 0.1

    if context and len(context) > 20:
        score += 0.05

    return round(min(max(score, 0.1), 1.0), 2)


def _deduplicate(items: list[dict], key_field: str, threshold: float = 0.70) -> list[dict]:
    """Remove near-duplicate items.

    FIX (Bug 5): in-place index replace instead of list.remove() mid-iteration.
    FIX (Bug K / loophole #6): threshold lowered to 0.70; text normalised before
    comparison so paraphrases of the same task are caught.
    """
    unique: list[dict] = []
    for item in items:
        # Normalise for comparison only (don't mutate the original)
        item_key = re.sub(r'\s+', ' ', item[key_field].lower().strip())
        replaced = False
        for i, existing in enumerate(unique):
            existing_key = re.sub(r'\s+', ' ', existing[key_field].lower().strip())
            if _similarity(item_key, existing_key) >= threshold:
                if item.get("confidence", 0) > existing.get("confidence", 0):
                    unique[i] = item
                replaced = True
                break
        if not replaced:
            unique.append(item)
    return unique


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_intelligence(processed_data: dict) -> dict:
    """Transform processed transcript data into high-value, deduplicated output.

    FIX (Bug 7): schema validated at entry; missing keys raise KeyError.
    FIX (Bug J / loophole #2): owner resolution tries "who", "owner", "assigned_to".
    FIX (Bug I / loophole #8): vague tasks flagged with needs_clarification=True.
    """
    missing = [k for k in ("decisions", "action_items") if k not in processed_data]
    if missing:
        raise KeyError(f"extract_intelligence: missing required keys: {missing}")

    raw_decisions = processed_data["decisions"]
    raw_actions = processed_data["action_items"]

    # ── Decisions ──────────────────────────────────────────────────────────
    decisions: list[dict] = []
    for d in raw_decisions:
        text = _normalize_text(d.get("decision", ""))
        if not text or len(text) < 5:
            continue
        context = d.get("context")
        decisions.append({
            "text": text,
            "priority": _score_priority(text),
            "confidence": _score_confidence(text, context),
        })
    decisions = _deduplicate(decisions, "text")

    # ── Action items ────────────────────────────────────────────────────────
    action_items: list[dict] = []
    for a in raw_actions:
        task = _normalize_text(a.get("what", ""))
        if not task or len(task) < 5:
            continue

        # FIX (Bug J): try all known owner-key aliases
        owner = (
            a.get("who") or a.get("owner") or a.get("assigned_to") or ""
        ).strip()
        if not owner or owner.lower() in {"unassigned", "unknown", "tbd", ""}:
            owner = "Unassigned"

        deadline = a.get("when")
        deadline = deadline.strip() if deadline else None

        context = a.get("context")
        priority = _score_priority(task, has_deadline=deadline is not None)
        confidence = _score_confidence(task, context)

        if owner == "Unassigned":
            confidence = round(max(confidence - 0.1, 0.1), 2)

        # FIX (Bug I / loophole #8): flag tasks too vague to calendar
        needs_clarification = _is_vague_task(task)

        # Carry forward upstream needs_review flag
        needs_review = a.get("needs_review", False)

        action_items.append({
            "owner": owner,
            "task": task,
            "deadline": deadline,
            "priority": priority,
            "confidence": confidence,
            "needs_clarification": needs_clarification,
            "needs_review": needs_review,
        })

    action_items = _deduplicate(action_items, "task")

    # ── Sort: HIGH first, then confidence desc ─────────────────────────────
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    decisions.sort(key=lambda x: (priority_order.get(x["priority"], 1), -x["confidence"]))
    action_items.sort(key=lambda x: (priority_order.get(x["priority"], 1), -x["confidence"]))

    return {
        "decisions": decisions,
        "action_items": action_items,
    }
