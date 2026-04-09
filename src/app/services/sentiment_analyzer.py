"""Meeting sentiment and tone analysis service.

Fix log
-------
Bug R  – segment_transcript: speaker detection regex now uses the same
         expanded charset as transcript_processor.detect_speakers so
         "Mary-Jane" and "O'Brien" are correctly segmented rather than
         their lines being treated as continuation text (loophole #11).
"""

import re
from typing import Optional


POSITIVE_WORDS = {
    'great', 'excellent', 'good', 'wonderful', 'fantastic', 'awesome', 'amazing',
    'happy', 'pleased', 'satisfied', 'excited', 'thrilled', 'delighted',
    'agree', 'agreed', 'approval', 'approve', 'approved', 'support', 'supported',
    'success', 'successful', 'succeeded', 'achieve', 'achieved', 'accomplish',
    'perfect', 'perfectly', 'best', 'better', 'impressive', 'impressed',
    'thank', 'thanks', 'appreciate', 'appreciated', 'grateful',
    'love', 'like', 'enjoy', 'enjoyed', 'looking forward',
    'confident', 'optimistic', 'positive', 'promising', 'encouraging',
    'solve', 'solved', 'resolved', 'fixed', 'improvement', 'improved',
    'welcome', 'glad', 'pleasure', 'benefit', 'beneficial', 'valuable',
    'yes', 'definitely', 'absolutely', 'exactly', 'correct', 'right',
    'clear', 'clearly', 'understood', 'helpful', 'forward', 'progress',
}

NEGATIVE_WORDS = {
    'bad', 'terrible', 'awful', 'horrible', 'poor', 'worst',
    'unhappy', 'disappointed', 'dissatisfied', 'frustrated', 'annoyed',
    'disagree', 'disagreed', 'disapproval', 'disapprove', 'concern', 'concerned',
    'fail', 'failed', 'failure', 'problem', 'problems', 'issue', 'issues',
    'wrong', 'error', 'errors', 'mistake', 'mistakes', 'bug', 'bugs',
    'difficult', 'difficulties', 'difficulty', 'challenge', 'challenges',
    'worry', 'worried', 'anxious', 'nervous', 'stress', 'stressed',
    'hate', 'dislike', 'unfortunately', 'sad', 'unlucky',
    'delay', 'delayed', 'late', 'behind', 'overdue',
    'conflict', 'dispute', 'argument', 'disagreement', 'tension',
    'risk', 'risky', 'danger', 'dangerous', 'threat', 'threatening',
    'expensive', 'costly', 'budget', 'over budget', 'cut', 'reduce',
    'reject', 'rejected', 'refuse', 'refused', 'deny', 'denied',
    'stop', 'cannot', "can't", "won't", 'never', 'fail',
}

AGREEMENT_PATTERNS = [
    r'\bI\s+agree\b', r"\bthat's\s+right\b", r'\bexactly\b', r'\byes\b',
    r'\bsure\b', r'\bcertainly\b', r'\babsolutely\b', r'\bdefinitely\b',
    r'\bI\s+think\s+so\s+too\b', r"\byou're\s+right\b", r'\bme\s+too\b',
    r'\bsounds\s+good\b', r'\bsounds\s+great\b', r'\bI\s+support\b',
    r'\bI\s+second\b', r'\bgo\s+ahead\b', r'\blet\'s\s+do\s+it\b',
    r'\bon\s+board\b', r'\baligned\b', r'\bin\s+agreement\b',
]

CONFLICT_PATTERNS = [
    r'\bI\s+disagree\b', r"\bI\s+don't\s+think\b", r"\bthat's\s+wrong\b",
    r'\bhowever\b', r'\bbut\b.*\bwrong\b', r'\bno\b.*\bproblem\b',
    r'\bwe\s+need\s+to\s+argue\b', r'\bthis\s+is\s+unacceptable\b',
    r'\bI\s+object\b', r'\bthat\s+won\'t\s+work\b', r'\bI\s+refuse\b',
    r'\bwe\s+have\s+a\s+conflict\b', r'\bthere\s+is\s+a\s+problem\b',
    r'\bdispute\b', r'\bnot\s+true\b', r'\bcounter\s+point\b',
]

CONCERN_PATTERNS = [
    r'\bI\'?m\s+worried\b', r'\bI\'?m\s+concerned\b', r'\bthis\s+is\s+a\s+concern\b',
    r'\bwe\s+need\s+to\s+worry\b', r'\bwhat\s+if\b', r'\bI\'?m\s+not\s+sure\b',
    r'\bI\s+have\s+doubts\b', r'\bthis\s+might\s+be\s+a\s+problem\b',
    r'\bI\s+hope\b.*\bworks\b', r'\blet\'?s\s+be\s+careful\b',
    r'\bwe\s+should\s+consider\b', r'\bwhat\s+about\b.*\brisk\b',
    r'\bpotential\s+issue\b', r'\bcryptic\b', r'\buncertain\b',
]

ENTHUSIASM_PATTERNS = [
    r'\bI\'?m\s+excited\b', r'\bthis\s+is\s+exciting\b', r'\bI\s+love\b',
    r'\bI\s+can\'?t\s+wait\b', r'\bgreat\s+idea\b', r'\bwonderful\b',
    r'\bfantastic\b', r'\bamazing\b', r'\bawesome\b',
    r'\blet\'?s\s+go\b', r'\bI\'?m\s+thrilled\b',
    r'\bthis\s+is\s+going\s+to\s+be\s+great\b', r'\bexcellent\b',
    r'\bbrilliant\b', r'\bperfect\b', r'\bcan\'t\s+wait\b',
]


def segment_transcript(clean_text: str) -> list[dict]:
    """Segment a transcript into logical segments by speaker.

    FIX (Bug R / loophole #11): speaker regex now uses the same expanded
    charset as transcript_processor.detect_speakers — hyphens and apostrophes
    included — so names like "Mary-Jane" and "O'Brien" are correctly identified
    as speaker boundaries rather than treated as continuation lines.
    """
    segments: list[dict] = []
    lines = clean_text.split('\n')

    current_speaker: Optional[str] = None
    current_text: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # FIX (Bug R): was r'^([A-Z][a-zA-Z0-9\s\.]+?)\s*:' — missed hyphens/apostrophes
        speaker_match = re.match(r"^([A-Z][a-zA-Z0-9\s\.\-']+?)\s*:", line)

        if speaker_match:
            if current_speaker and current_text:
                segments.append({
                    "speaker": current_speaker,
                    "text": ' '.join(current_text),
                })
            current_speaker = speaker_match.group(1).strip()
            text_after = line[speaker_match.end():].strip()
            current_text = [text_after] if text_after else []
        else:
            if current_speaker:
                current_text.append(line)

    if current_speaker and current_text:
        segments.append({
            "speaker": current_speaker,
            "text": ' '.join(current_text),
        })

    return segments


def analyze_sentiment(text: str) -> str:
    """Analyze the sentiment of a text segment."""
    words = re.findall(r'\b\w+\b', text.lower())
    pos = sum(1 for w in words if w in POSITIVE_WORDS)
    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
    if pos > neg:
        return "Positive"
    if neg > pos:
        return "Negative"
    return "Neutral"


def detect_tone(text: str) -> Optional[str]:
    """Detect the dominant tone in a text segment."""
    text_lower = text.lower()
    scores = {
        "Agreement":  sum(1 for p in AGREEMENT_PATTERNS  if re.search(p, text_lower)),
        "Conflict":   sum(1 for p in CONFLICT_PATTERNS   if re.search(p, text_lower)),
        "Concern":    sum(1 for p in CONCERN_PATTERNS    if re.search(p, text_lower)),
        "Enthusiasm": sum(1 for p in ENTHUSIASM_PATTERNS if re.search(p, text_lower)),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def analyze_transcript_sentiment(clean_text: str) -> dict:
    """Analyze sentiment and tone for an entire transcript."""
    segments = segment_transcript(clean_text)
    timeline: list[dict] = []
    speaker_sentiments: dict[str, list[str]] = {}
    speaker_tones: dict[str, list[str]] = {}

    for segment in segments:
        speaker = segment["speaker"]
        text = segment["text"]
        sentiment = analyze_sentiment(text)
        tone = detect_tone(text)

        timeline.append({
            "segment": text,
            "sentiment": sentiment,
            "tone": tone,
            "speaker": speaker,
        })

        speaker_sentiments.setdefault(speaker, []).append(sentiment)
        if tone:
            speaker_tones.setdefault(speaker, []).append(tone)

    speaker_summary: list[dict] = []
    for speaker, sentiments in speaker_sentiments.items():
        pos = sentiments.count("Positive")
        neg = sentiments.count("Negative")
        overall = "Positive" if pos > neg else ("Negative" if neg > pos else "Neutral")

        tones = speaker_tones.get(speaker, [])
        dominant_tone: Optional[str] = None
        if tones:
            tone_counts: dict[str, int] = {}
            for t in tones:
                tone_counts[t] = tone_counts.get(t, 0) + 1
            dominant_tone = max(tone_counts, key=tone_counts.get)

        speaker_summary.append({
            "speaker": speaker,
            "overall_sentiment": overall,
            "dominant_tone": dominant_tone,
        })

    return {
        "timeline": timeline,
        "speaker_summary": speaker_summary,
    }
