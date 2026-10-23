"""Evidence-anchored structured meeting extraction.

Produces the enterprise extraction contract for a single meeting transcript,
regardless of whether the transcript was typed by a user or read from an
uploaded ``.txt`` / ``.vtt`` file:

    {
      "meeting_title": str | None,
      "summary": str,
      "decisions": [{"decision": str, "evidence": str}],
      "tasks": [{"title": str, "description": str | None,
                 "assignee": str | None, "due_date": str | None,
                 "evidence": str}],
      "blockers": [{"issue": str, "evidence": str}]
    }

Grounding rules enforced throughout this module
------------------------------------------------
R1  Nothing is emitted that the transcript does not explicitly support.
R2  Every decision / task / blocker carries the verbatim transcript line as
    ``evidence`` (speaker label preserved).
R3  ``assignee`` is null unless a named person appears in the transcript and
    matches a detected speaker — collective phrasing ("we", "the team") and
    pronouns never resolve to an individual.
R4  ``due_date`` is null unless a date is stated *and* resolves to an ISO
    ``YYYY-MM-DD`` value; unresolvable dates degrade to null rather than
    being guessed.
R5  Suggestions, hedged opinions and open debate are not decisions.
R6  An empty or missing transcript yields nulls and empty lists — never
    invented content.
"""

import re
from collections import Counter
from typing import Optional

from app.services.transcript_processor import (
    clean_transcript,
    detect_speakers,
    extract_meeting_date,
    resolve_deadline,
)


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------

_SPEAKER_LINE_RE = re.compile(r"^([A-Z][a-zA-Z0-9\s\.\-']+?)\s*:\s*(.*)$")

# WebVTT preamble metadata — not conversation.
_VTT_HEADER_RE = re.compile(
    r"^(?:WEBVTT|NOTE|STYLE|REGION)\b|^(?:Kind|Language)\s*:",
    re.IGNORECASE,
)

# Leading words that look like a speaker label but are actually section
# headings written by humans ("Action Item: ...", "Decision: ...").
_LABEL_PREFIXES = frozenset({
    "transcript", "subtitle", "caption", "note", "notes", "context",
    "background", "quote", "example", "action item", "action items", "task",
    "tasks", "todo", "to-do", "to do", "decision", "decisions", "agreed",
    "summary", "update", "updates", "risk", "risks", "blocker", "blockers",
    "question", "questions", "open question", "open questions", "issue",
    "issues", "item", "items", "meeting", "agenda", "topic", "subject",
    "date", "attendees", "participants", "warning", "result", "results",
    "outcome", "outcomes", "follow up", "follow-up", "next steps",
    "next step", "re", "from", "to", "cc",
})


def _is_speaker_label(candidate: str) -> bool:
    """True when a leading ``Word(s):`` segment really is a speaker name."""
    candidate = candidate.strip()
    if not candidate or len(candidate.split()) > 4:
        return False
    if candidate.lower() in _LABEL_PREFIXES:
        return False
    # "We agreed", "The team" etc. are sentence openings, not names.
    first_word = candidate.split()[0].lower()
    if first_word in {"we", "i", "they", "he", "she", "it", "the", "this",
                      "that", "these", "those", "there", "and", "but", "so",
                      "also", "then", "next", "ok", "okay", "alright"}:
        return False
    return True


def parse_utterances(clean_text: str) -> list[dict]:
    """Split a cleaned transcript into speaker-attributed utterances.

    Returns a list of ``{"speaker", "text", "evidence"}`` dicts in transcript
    order. ``evidence`` is the original line (speaker label included) so the
    extraction contract can quote it verbatim.
    """
    utterances: list[dict] = []
    current_speaker = "Unknown"

    for raw_line in clean_text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        # Skip the WebVTT preamble until the first real utterance.
        if not utterances and _VTT_HEADER_RE.match(line):
            continue

        body = line
        match = _SPEAKER_LINE_RE.match(line)
        if match:
            candidate = match.group(1).strip()
            rest = match.group(2).strip()
            if rest and _is_speaker_label(candidate):
                current_speaker = candidate
                body = rest

        if not body:
            continue

        utterances.append({
            "speaker": current_speaker,
            "text": body,
            "evidence": line,
        })

    return utterances


def observed_speakers(utterances: list[dict]) -> list[str]:
    """Speaker labels actually used by utterances, in first-seen order."""
    seen: list[str] = []
    for utterance in utterances:
        speaker = utterance["speaker"]
        if speaker.lower() in {"unknown", "unassigned"}:
            continue
        if speaker not in seen:
            seen.append(speaker)
    return seen


def sanitize_speakers(speakers: list[str], utterances: list[dict]) -> list[str]:
    """Drop section-heading pseudo-speakers ("Meeting", "Date", "Action Item").

    ``detect_speakers`` uses a narrower label blacklist than
    :func:`parse_utterances`, so header lines such as ``Meeting: Q3 Sync`` can
    leak in as speaker names. Its ``\\s``-based label regex can also span line
    breaks (a VTT ``WEBVTT`` header directly above ``Alice:`` yields the label
    ``"WEBVTT\\n\\nAlice"``), so multi-line labels are rejected here too.
    """
    merged: list[str] = []
    for speaker in [*speakers, *observed_speakers(utterances)]:
        low = speaker.lower()
        if low in _LABEL_PREFIXES or low in {"unknown", "unassigned"}:
            continue
        if "\n" in speaker or re.search(r"\s{2,}", speaker):
            continue
        if speaker not in merged:
            merged.append(speaker)
    return merged


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Collapse whitespace and tidy casing for output fields."""
    text = re.sub(r"\s+", " ", text or "").strip()
    text = text.strip(" \t\n-–—:;,.")
    if text:
        text = text[0].upper() + text[1:]
    return text


def _similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher

    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _deduplicate(items: list[dict], key: str, threshold: float = 0.80) -> list[dict]:
    """Drop near-duplicate items, keeping the first (most faithful) occurrence."""
    unique: list[dict] = []
    for item in items:
        normalized = re.sub(r"\s+", " ", item[key].lower().strip())
        if any(
            _similarity(normalized, re.sub(r"\s+", " ", u[key].lower().strip()))
            >= threshold
            for u in unique
        ):
            continue
        unique.append(item)
    return unique


# ---------------------------------------------------------------------------
# Deadline extraction (R4)
# ---------------------------------------------------------------------------

_DUE_RE = re.compile(
    r"\b(?:by|before|until|due(?:\s+on)?|no\s+later\s+than)\s+"
    r"([^.,;?\n]+)",
    re.IGNORECASE,
)

_MONTHS = (
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
)

# Concrete dates stated without a "by/before" connector. Deliberately narrow:
# vague urgency words ("ASAP", "soon") are excluded because they do not name
# a date (R4).
_STANDALONE_DATE_RE = re.compile(
    r"\b(?:"
    r"today|tonight|tomorrow"
    r"|eod|cob|eob|end\s+of\s+(?:the\s+)?(?:day|week|month)"
    r"|next\s+(?:week|month)"
    r"|mon|tues|wednes|thurs|fri|satur|sun[a-z]*day"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    rf"|{_MONTHS}\s+\d{{1,2}}"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTHS}"
    r")\b",
    re.IGNORECASE,
)


def extract_due_date(text: str, meeting_date: Optional[str]) -> Optional[str]:
    """Return an ISO due date only when the transcript states one.

    Unresolvable phrasing ("by the end of the phase", "by EOD-ish") resolves
    to ``None`` rather than an invented date (R4).
    """
    candidates: list[str] = []

    match = _DUE_RE.search(text)
    if match:
        candidates.append(match.group(1).strip())

    standalone = _STANDALONE_DATE_RE.search(text)
    if standalone:
        candidates.append(standalone.group(0).strip())

    for raw in candidates:
        if not raw:
            continue
        resolved = resolve_deadline(raw, meeting_date)
        if resolved and "[UNRESOLVED]" not in resolved:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", resolved):
                return resolved
    return None


def _strip_deadline_clause(text: str) -> str:
    """Remove a trailing deadline clause so task titles stay readable."""
    stripped = _DUE_RE.sub("", text)
    return re.sub(r"\s+", " ", stripped).strip(" ,;-")


def _shorten(text: str, limit: int = 110) -> str:
    """Cap a title at a word boundary."""
    if len(text) <= limit:
        return text
    clipped = text[:limit].rsplit(" ", 1)[0]
    return clipped.rstrip(" ,;-")


# ---------------------------------------------------------------------------
# Decision extraction (R5)
# ---------------------------------------------------------------------------

_DECISION_PATTERNS = [
    r"\b(?:we|the\s+team|everyone|all\s+of\s+us)\s+(?:have\s+|has\s+|had\s+)?"
    r"(?:decided|agreed|resolved|concluded|finalized|finalised|approved|"
    r"confirmed|settled\s+on|locked\s+in|gone\s+with|going\s+with)\s+"
    r"(?:to\s+|on\s+|that\s+|for\s+)?(?P<detail>[^.\n!?;]+)",

    r"\b(?:it(?:'s|\s+is)\s+|we\s+have\s+)?"
    r"(?:decided|agreed|approved|confirmed|finalized|finalised|resolved|"
    r"settled)\s+(?:that\s+|to\s+|on\s+)?(?P<detail>[^.\n!?;]+)",

    r"\b(?:the\s+)?(?:final\s+|official\s+)?decision\s*(?:is|:)\s*"
    r"(?P<detail>[^.\n!?;]+)",

    r"\b(?:let'?s|lets\s+us|we\s+will)\s+go\s+with\s+(?P<detail>[^.\n!?;]+)",

    r"\b(?:we(?:'re|\s+are)|proceeding)\s+(?:going\s+with|settled\s+on|"
    r"proceeding\s+with|moving\s+forward\s+with)\s+(?P<detail>[^.\n!?;]+)",

    r"\b(?:approved|signed\s+off\s+on|greenlit|green-lit)\s*[:\-]?\s*"
    r"(?P<detail>[^.\n!?;]+)",
]

# Hedged / speculative language — proves the topic was discussed, not decided.
_NON_FINAL_RE = re.compile(
    r"\b(?:maybe|perhaps|possibly|might|could|should\s+we|let'?s\s+consider|"
    r"consider|considering|propose|proposed|suggest|suggested|what\s+if|"
    r"wondering|wonder|leaning\s+towards?|leaning\s+toward|not\s+decided|"
    r"undecided|tentative|tentatively|provisionally|potentially|ideally|"
    r"for\s+now|open\s+to|debate|revisit|revisited|tbd|to\s+be\s+decided|"
    r"to\s+be\s+confirmed|pending\s+confirmation|under\s+discussion|"
    r"discuss|discussed|opinion|thoughts?)\b",
    re.IGNORECASE,
)

_MIN_DETAIL_LEN = 8


def extract_decisions(utterances: list[dict]) -> list[dict]:
    """Extract finalized decisions with their verbatim evidence."""
    decisions: list[dict] = []

    for utterance in utterances:
        text = utterance["text"]
        for pattern in _DECISION_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue

            detail = _normalize(match.group("detail"))
            if len(detail) < _MIN_DETAIL_LEN:
                continue

            # R5 — hedged phrasing disqualifies the line as a decision.
            window = f"{match.group(0)} {match.group('detail')}"
            if _NON_FINAL_RE.search(window):
                continue

            decisions.append({
                "decision": _shorten(detail),
                "evidence": utterance["evidence"],
            })
            break

    return _deduplicate(decisions, "decision")


# ---------------------------------------------------------------------------
# Task extraction (R3 / R4)
# ---------------------------------------------------------------------------

_OWNER_TOKEN = r"[A-Z][A-Za-z0-9\.\-']{1,24}"

_TASK_PATTERNS = [
    # Explicit labels: "Action item - Sarah: send the contract"
    rf"\b(?:action\s+item|action\s+items|todo|to-do|task)\s*"
    rf"(?:for|assigned\s+to|owner)\s+(?P<owner>{_OWNER_TOKEN}(?:\s+{_OWNER_TOKEN})?)\s*[:\-]\s*"
    rf"(?P<detail>[^.\n!?]+)",

    rf"\b(?:action\s+item|action\s+items|todo|to-do|task)\s*[:\-]\s*"
    rf"(?P<detail>[^.\n!?]+)",

    # Self-assignment: "I'll send the deck"
    r"\b(?:i|i'?ll|i'?m\s+going\s+to)\s+(?:will|can|shall|am\s+going\s+to|"
    r"'?m\s+going\s+to)?\s*(?P<detail>(?:will\s+|to\s+|need\s+to\s+|"
    r"should\s+)?[^.\n!?]+)",

    # Passive assignment: "The migration plan is assigned to Marcus."
    rf"(?P<detail>[^.\n!?]+?)\s+(?:is|are|was|were|has\s+been|have\s+been)\s+"
    rf"(?:assigned\s+to|owned\s+by|handled\s+by)\s+(?P<owner>{_OWNER_TOKEN}(?:\s+{_OWNER_TOKEN})?)"
    rf"(?=[.,;:\n]|$)",

    # Named owner + commitment modal: "Priya will draft the rollout plan."
    rf"\b(?P<owner>{_OWNER_TOKEN})\s+(?:will|needs?\s+to|has\s+to|must|"
    rf"is\s+going\s+to|should|is\s+taking\s+on|owns|is\s+responsible\s+for|"
    rf"can\s+take\s+care\s+of|can\s+handle|is\s+on)\s+(?P<detail>[^.\n!?]+)",

    # Polite request: "Please confirm the numbers."
    r"\bplease\s+(?P<detail>[^.\n!?]+)",
]

# Hedged phrasing — a suggestion is not a confirmed task.
_SUGGESTION_RE = re.compile(
    r"\b(?:maybe|perhaps|might|could|possibly|probably|likely|presumably|"
    r"should\s+we|let'?s\s+see|consider|suggest|propose|what\s+if|assuming|"
    r"if\s+we|ideally|potentially|would\s+be\s+nice|could\s+we|"
    r"do\s+we\s+need\s+to|feel\s+free\s+to)\b",
    re.IGNORECASE,
)

_SELF_REF_RE = re.compile(r"^\s*(?:i|i'?ll|i'?m|we'?ll|we'?re)\b", re.IGNORECASE)

# Never resolve an owner to a pronoun or collective — they are not people (R3).
_NON_PERSON_OWNERS = frozenset({
    "we", "i", "he", "she", "they", "it", "us", "them", "him", "her",
    "the team", "team", "everyone", "everybody", "all of us", "all",
    "someone", "somebody", "anyone", "anybody", "nobody", "no one",
    "group", "both", "each", "one", "people", "folks", "guys", "everyone else",
    "should", "need", "needs", "must", "will", "can", "let", "lets",
})

_MIN_TASK_LEN = 6


def _resolve_assignee(
    raw_owner: Optional[str],
    utterance: dict,
    speakers: list[str],
) -> Optional[str]:
    """Map a candidate owner onto a detected speaker, else ``None`` (R3)."""
    if raw_owner:
        candidate = raw_owner.strip()
        if candidate.lower() in _NON_PERSON_OWNERS:
            return None
        for speaker in speakers:
            if speaker.lower() == candidate.lower():
                return speaker
        # A named person who never speaks is still explicitly identified.
        if candidate and candidate.lower() not in {"unknown", "unassigned"}:
            if len(candidate.split()) <= 4:
                return candidate
        return None

    # Self-assignment → the speaker, provided they were identified.
    if _SELF_REF_RE.match(utterance["text"]):
        speaker = utterance["speaker"]
        if speaker and speaker.lower() not in {"unknown", "unassigned"}:
            return speaker

    # Otherwise look for any detected speaker named inside the line.
    for speaker in speakers:
        if speaker.lower() in {"unknown", "unassigned"}:
            continue
        if re.search(rf"\b{re.escape(speaker)}\b", utterance["text"], re.IGNORECASE):
            return speaker

    return None


def extract_tasks(
    utterances: list[dict],
    speakers: list[str],
    meeting_date: Optional[str],
) -> list[dict]:
    """Extract confirmed tasks with assignee / due date only when stated."""
    tasks: list[dict] = []

    for utterance in utterances:
        text = utterance["text"]

        # An open question is not a commitment.
        if text.rstrip().endswith("?"):
            continue

        for pattern in _TASK_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue

            detail = _normalize(_strip_deadline_clause(match.group("detail")))
            if len(detail) < _MIN_TASK_LEN:
                continue

            # Strip a leading modal that leaked into the captured clause.
            detail = re.sub(
                r"^(?:to|will|needs?\s+to|has\s+to|must|should|going\s+to|"
                r"take\s+care\s+of|handle)\s+",
                "",
                detail,
                flags=re.IGNORECASE,
            ).strip()
            detail = _normalize(detail)
            if len(detail) < _MIN_TASK_LEN:
                continue

            if _SUGGESTION_RE.search(match.group(0) + " " + detail):
                continue

            assignee = _resolve_assignee(
                match.groupdict().get("owner"), utterance, speakers
            )
            due_date = extract_due_date(text, meeting_date)

            tasks.append({
                "title": _shorten(detail),
                "description": _normalize(utterance["text"]) or None,
                "assignee": assignee,
                "due_date": due_date,
                "evidence": utterance["evidence"],
            })
            break

    return _deduplicate(tasks, "title")


# ---------------------------------------------------------------------------
# Blocker / risk / open-question extraction
# ---------------------------------------------------------------------------

_BLOCKER_PATTERNS = [
    r"\b(?:blocked|blocker|blocking|stuck\s+on|held\s+up)\b",
    r"\b(?:depends?\s+on|dependent\s+on|waiting\s+on|pending\s+on)\b",
    r"\bat\s+risk\b",
    r"\brisk\b",
    r"\b(?:blocked\s+by)\b",
    r"\b(?:needs?|requires?)\s+(?:approval|sign[- ]off|signoff|review)\b",
    r"\b(?:open\s+question|open\s+issues?|unknown|unsure|not\s+sure|unclear|"
    r"tbd|to\s+be\s+determined|need\s+to\s+confirm|haven'?t\s+decided|"
    r"don'?t\s+know)\b",
    r"\b(?:can'?t|cannot|unable\s+to|no\s+access\s+to|"
    r"don'?t\s+have\s+access\s+to|out\s+of\s+office|unavailable|"
    r"no\s+longer\s+available)\b",
    r"\b(?:behind\s+schedule|delayed|delay|slipping|slipped|postponed|"
    r"pushed\s+back|overdue)\b",

    # Resource constraints — a bare mention of "budget" is not a problem.
    r"\b(?:over\s+budget|under\s+budget|budget\s+(?:constraint|cut|cuts|issue|"
    r"problem|gap|limit|tight|short|approval|shortfall)|no\s+budget|"
    r"budget\s+is\s+(?:tight|short|limited)|"
    r"headcount\s+(?:freeze|cut|cuts|issue|constraint|gap|reduction)|"
    r"no\s+headcount|"
    r"capacity\s+(?:issue|constraint|problem|gap|limit|shortage)|"
    r"no\s+capacity|limited\s+capacity|capacity\s+is\s+(?:limited|tight)|"
    r"time\s+constraint|limited\s+time|out\s+of\s+time)\b",

    r"\b(?:issue|problem|gap|concern|pain\s+point)\b",
    r"\b(?:constraints?|limitations?|shortages?)\b",
    r"\b(?:if\s+we\s+don'?t|unless)\b",
]

# "No blockers", "not at risk" — the absence of a problem is not a blocker.
_BLOCKER_NEGATION_RE = re.compile(
    r"\b(?:no|not|none|without|nothing|zero|any)\s+"
    r"(?:blockers?|risks?|issues?|concerns?|problems?|dependencies?|"
    r"obstacles?)\b"
    r"|\b(?:unblocked|nothing\s+blocking|not\s+blocked|no\s+blockers|"
    r"nothing\s+to\s+flag|all\s+clear|no\s+objections?|no\s+objection)\b"
    r"|\bnot\s+at\s+risk\b",
    re.IGNORECASE,
)


def extract_blockers(utterances: list[dict]) -> list[dict]:
    """Extract risks, blockers, dependencies, constraints and open questions."""
    blockers: list[dict] = []

    for utterance in utterances:
        text = utterance["text"]

        if _BLOCKER_NEGATION_RE.search(text):
            continue

        # An explicit question (minus logistics noise) is an open question.
        if text.rstrip().endswith("?"):
            if not _LOGISTICS_QUESTION_RE.search(text):
                blockers.append({
                    "issue": _shorten(_normalize(text), 200),
                    "evidence": utterance["evidence"],
                })
            continue

        for pattern in _BLOCKER_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue

            # Report the speaker's full turn so no context is lost.
            issue = _normalize(text)
            if len(issue) < _MIN_TASK_LEN:
                continue

            blockers.append({
                "issue": _shorten(issue, 200),
                "evidence": utterance["evidence"],
            })
            break

    return _deduplicate(blockers, "issue")


_LOGISTICS_QUESTION_RE = re.compile(
    r"\b(?:can\s+(?:you|everyone|we|somebody)\s+hear|are\s+you\s+(?:there|on|"
    r"muted)|can\s+you\s+hear\s+me|let'?s\s+(?:start|begin|get\s+started)|"
    r"shall\s+we\s+(?:start|begin)|any\s+(?:questions|objections|"
    r"anything\s+else)|is\s+everyone\s+(?:here|on)|do\s+you\s+(?:hear|see)|"
    r"you'?re\s+(?:muted|frozen)|can\s+you\s+repeat)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Title & summary
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset("""
a about above after again against all also am an and any are aren as at be because
been before being below between both but by can cannot could couldn did didn do does
doesn doing don down during each few for from further had hadn has hasn have haven
having he her here hers herself him himself his how i if in into is isn it its
itself just let ll me more most much must my myself no nor not of off on once only or
other ought our ours ourselves out over own re same shan she should shouldn so some
such than that the their theirs them themselves then there these they this those
through to too under until up ve very was wasn we were weren what when where which
while who whom why will with won would wouldn you your yours yourself yourselves
""".split())

_NOISE_WORDS = frozenset("""
meeting meetings note notes minutes hello hi hey alright okay ok thanks thank
please everyone folks guys team date agenda recap update updates review
follow next steps action items task items transcript recording
webvtt kind language captions caption subtitles subtitle speaker speakers audio
monday tuesday wednesday thursday friday saturday sunday today tomorrow yesterday
week weeks month months year years quarter
january february march april may june july august september october november
december call sync standup stand recap something anything everything nothing
probably likely maybe perhaps other others same thing things point first second
last one ones bit lot kick kickoff welcome
let lets let's agreed agree decided decide approving approve approved confirm confirmed
finalized finalized proceeding proceeding revisit revisiting moved moving
might must should could would
consider considering
""".split())

_EXPLICIT_TITLE_RE = re.compile(
    r"^\s*(?:meeting|agenda|topic|subject|title|re)\s*[:\-]\s*(?P<title>.+)$",
    re.IGNORECASE | re.MULTILINE,
)

_DATE_LABEL_RE = re.compile(
    r"^\s*(?:meeting\s+date|date|held\s+on|when|on)\s*[:\-]\s*(?P<date>.+)$",
    re.IGNORECASE,
)


def meeting_date_from_header(clean_text: str) -> Optional[str]:
    """Return the meeting date only when it appears in a header position.

    ``extract_meeting_date`` matches any date anywhere in the transcript, which
    is the right anchor for resolving *relative* deadlines but the wrong value
    for "when did this meeting happen" — a task due 2026-10-15 must not become
    the meeting date. Only a labelled or leading header line is accepted.
    """
    for raw_line in clean_text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        labelled = _DATE_LABEL_RE.match(line)
        if labelled:
            found = extract_meeting_date(labelled.group("date"))
            if found:
                return found

        # The first speaker turn ends the header block — dates after it belong
        # to the conversation, not to the meeting.
        speaker_match = _SPEAKER_LINE_RE.match(line)
        if speaker_match and _is_speaker_label(speaker_match.group(1)):
            break

        # An unlabelled date counts only while still in the preamble.
        if len(line) <= 60:
            found = extract_meeting_date(line)
            if found:
                return found

    return None


def build_meeting_title(
    clean_text: str,
    utterances: list[dict],
    speakers: list[str],
    meeting_date: Optional[str],
    exclude: Optional[set[str]] = None,
) -> Optional[str]:
    """Derive a short descriptive title from transcript content only."""
    if not utterances:
        return None

    explicit = _EXPLICIT_TITLE_RE.search(clean_text)
    if explicit:
        candidate = explicit.group("title").strip().strip("*#- ")
        candidate = re.sub(r"\s+", " ", candidate)
        if 3 <= len(candidate) <= 120:
            return candidate

    excluded = {s.lower() for s in (exclude or set())}
    speaker_names = {s.lower() for s in speakers}
    counts: Counter = Counter()
    for utterance in utterances:
        for token in re.findall(r"[A-Za-z][A-Za-z'\-]{2,}", utterance["text"]):
            low = token.lower()
            if (
                low in _STOPWORDS
                or low in _NOISE_WORDS
                or low in speaker_names
                or low in excluded
                or len(token) < 4
                or low.isdigit()
            ):
                continue
            counts[token] += 1

    top = [word for word, _ in counts.most_common(3)]
    if top:
        return " ".join(word if word[0].isupper() else word.capitalize() for word in top)

    named = [s for s in speakers if s.lower() not in {"unknown", "unassigned"}]
    if named:
        return "Meeting with " + ", ".join(named[:3])
    if meeting_date:
        return f"Meeting {meeting_date}"
    return "Meeting Notes"


_NO_EXTRACTION_SUMMARY = (
    "No transcript content was provided, so no meeting title, decisions, "
    "action items, or blockers could be extracted."
)


def build_summary(
    speakers: list[str],
    meeting_date: Optional[str],
    decisions: list[dict],
    tasks: list[dict],
    blockers: list[dict],
) -> str:
    """Build a 2–3 sentence summary composed only of extracted facts."""
    if not decisions and not tasks and not blockers:
        return _NO_EXTRACTION_SUMMARY

    named = [s for s in speakers if s.lower() not in {"unknown", "unassigned"}]
    if named:
        who = ", ".join(named[:-1]) + f" and {named[-1]}" if len(named) > 1 else named[0]
        if len(named) > 4:
            who = f"{len(named)} speakers"
    else:
        who = "Unidentified speakers"

    parts: list[str] = []
    if decisions:
        count = len(decisions)
        parts.append(f"{count} finalized decision{'s' if count != 1 else ''}")
    if tasks:
        count = len(tasks)
        parts.append(f"{count} action item{'s' if count != 1 else ''}")
    if blockers:
        count = len(blockers)
        parts.append(f"{count} flagged risk or open question{'s' if count != 1 else ''}")

    if len(parts) == 1:
        listed = parts[0]
    else:
        listed = ", ".join(parts[:-1]) + " and " + parts[-1]

    date_clause = f" on {meeting_date}" if meeting_date else ""
    sentences = [f"{who} met{date_clause} and recorded {listed}."]

    dated = [t for t in tasks if t["due_date"]]

    if decisions:
        sentences.append(f'The key decision was "{decisions[0]["decision"]}".')
    elif tasks:
        owner = tasks[0]["assignee"] or "no named owner"
        sentences.append(
            f'The leading action item, owned by {owner}, is "{tasks[0]["title"]}".'
        )
    elif blockers:
        sentences.append(f'The key issue raised was "{blockers[0]["issue"]}".')

    # A third sentence is added only when it contributes new information.
    if len(sentences) < 3:
        if dated:
            sentences.append(
                f"{len(dated)} of {len(tasks)} action item"
                f"{'s carry' if len(tasks) != 1 else ' carries'} a stated deadline."
            )
        else:
            others = len(blockers) if (decisions or tasks) else len(blockers) - 1
            if others > 0:
                sentences.append(
                    f"{others} other risk or open question"
                    f"{'s were' if others != 1 else ' was'} flagged."
                )

    return " ".join(sentences[:3])


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_structured_report(raw_transcript: Optional[str]) -> dict:
    """Extract the structured meeting report from a raw transcript.

    Accepts transcript text regardless of origin — typed by the user or read
    from an uploaded ``.txt`` / ``.vtt`` file.

    Raises:
        Nothing. An empty transcript yields ``None`` fields and empty lists.
    """
    if not raw_transcript or not raw_transcript.strip():
        return {
            "meeting_title": None,
            "summary": _NO_EXTRACTION_SUMMARY,
            "decisions": [],
            "tasks": [],
            "blockers": [],
        }

    clean_text = clean_transcript(raw_transcript)
    utterances = parse_utterances(clean_text)
    speakers = sanitize_speakers(detect_speakers(clean_text), utterances)

    # Two different dates: the anchor resolves relative deadlines ("Friday"),
    # while the header date describes when the meeting happened.
    anchor_date = extract_meeting_date(clean_text)
    meeting_date = meeting_date_from_header(clean_text)

    decisions = extract_decisions(utterances)
    tasks = extract_tasks(utterances, speakers, anchor_date)

    # A commitment that already carries an owner is a task, not a decision.
    task_titles = [t["title"] for t in tasks]
    decisions = [
        d for d in decisions
        if not any(_similarity(d["decision"], t) >= 0.80 for t in task_titles)
    ]

    blockers = extract_blockers(utterances)

    # An utterance cannot be both a commitment and a blocker.
    task_evidence = {t["evidence"] for t in tasks}
    blockers = [b for b in blockers if b["evidence"] not in task_evidence]

    assignees = {t["assignee"] for t in tasks if t["assignee"]}

    return {
        "meeting_title": build_meeting_title(
            clean_text, utterances, speakers, meeting_date, exclude=assignees
        ),
        "summary": build_summary(speakers, meeting_date, decisions, tasks, blockers),
        "decisions": decisions,
        "tasks": tasks,
        "blockers": blockers,
    }