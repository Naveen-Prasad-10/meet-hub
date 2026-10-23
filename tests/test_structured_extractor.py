"""Tests for the evidence-anchored structured extraction feature."""

import io
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.structured_extractor import (
    extract_structured_report,
    parse_utterances,
    sanitize_speakers,
)
from app.services.transcript_processor import clean_transcript

CONTRACT_KEYS = {"meeting_title", "summary", "decisions", "tasks", "blockers"}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


TRANSCRIPT = """Meeting: Q3 Pricing Launch Sync
Date: 2026-09-28
Sarah: We decided to ship the new pricing page on October 15.
Marcus: Priya will draft the migration plan by Friday.
Priya: I'm blocked on the legal sign-off.
Dana: Our team can't access the staging environment yet.
Sarah: Let's consider a discount tier, maybe January works.
Marcus: Can everyone hear me?
"""


# ─── Contract shape ────────────────────────────────────────────────────────

def test_empty_transcript_yields_no_hallucinated_content():
    report = extract_structured_report("")

    assert set(report) == CONTRACT_KEYS
    assert report["meeting_title"] is None
    assert report["decisions"] == []
    assert report["tasks"] == []
    assert report["blockers"] == []
    assert "no transcript content" in report["summary"].lower()


def test_whitespace_only_transcript_is_treated_as_empty():
    assert extract_structured_report("   \n\n  ")["meeting_title"] is None


def test_report_matches_contract_keys():
    assert set(extract_structured_report(TRANSCRIPT)) == CONTRACT_KEYS


def test_items_carry_evidence():
    report = extract_structured_report(TRANSCRIPT)

    for bucket in ("decisions", "tasks", "blockers"):
        assert report[bucket], f"{bucket} should not be empty"
        for item in report[bucket]:
            assert item["evidence"]
            assert item["evidence"] in TRANSCRIPT


# ─── Parsing ───────────────────────────────────────────────────────────────

def test_speaker_labels_are_not_treated_as_speakers():
    utterances = parse_utterances("Meeting: Q3 Sync\nSarah: Hello there")
    assert utterances[0]["speaker"] == "Unknown"
    assert utterances[1]["speaker"] == "Sarah"
    assert utterances[1]["evidence"] == "Sarah: Hello there"


def test_continuation_lines_stay_with_the_current_speaker():
    utterances = parse_utterances("Sarah: First point\nsecond point")
    assert [u["speaker"] for u in utterances] == ["Sarah", "Sarah"]


def test_section_headings_are_filtered_from_speakers():
    assert sanitize_speakers(["Meeting", "Date", "Sarah"], []) == ["Sarah"]


def test_multiline_vtt_labels_are_rejected():
    # detect_speakers can capture "WEBVTT\n\nAlice" as one label.
    assert sanitize_speakers(["WEBVTT\n\nAlice", "Bob"], []) == ["Bob"]


def test_vtt_preamble_is_not_treated_as_content():
    vtt = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:09.000\n"
        "Alice: We agreed to defer the hiring plan.\n"
    )
    utterances = parse_utterances(clean_transcript(vtt))

    assert [u["speaker"] for u in utterances] == ["Alice"]
    assert all("WEBVTT" not in u["text"] for u in utterances)
    assert "WEBVTT" not in (extract_structured_report(vtt)["meeting_title"] or "")


# ─── Meeting date vs. task deadline ────────────────────────────────────────

def test_task_due_date_does_not_become_the_meeting_date():
    transcript = (
        "Ana: Ben will send the forecast by 2026-10-15.\n"
        "Ben: We agreed to review it after that.\n"
    )
    report = extract_structured_report(transcript)

    assert report["tasks"][0]["due_date"] == "2026-10-15"
    assert "2026-10-15" not in report["summary"].split("met")[-1].split(".")[0]


def test_header_date_is_used_for_relative_deadlines():
    transcript = "Meeting: Ops\nDate: 2026-09-28\nAna: Ben will file the report tomorrow."
    task = extract_structured_report(transcript)["tasks"][0]
    assert task["due_date"] == "2026-09-29"


def test_mentioning_budget_alone_is_not_a_blocker():
    transcript = "Ana: Let's kick off the budget review."
    assert extract_structured_report(transcript)["blockers"] == []


def test_actual_budget_constraint_is_a_blocker():
    transcript = "Ana: We're over budget on the pilot."
    assert len(extract_structured_report(transcript)["blockers"]) == 1


# ─── Decisions ─────────────────────────────────────────────────────────────

def test_finalized_decision_is_extracted():
    decisions = extract_structured_report(TRANSCRIPT)["decisions"]
    assert any("ship the new pricing page" in d["decision"].lower() for d in decisions)


def test_suggestions_are_not_decisions():
    report = extract_structured_report(TRANSCRIPT)
    assert not any("discount tier" in d["decision"].lower() for d in report["decisions"])


def test_hedged_language_disqualifies_a_decision():
    transcript = "Dana: We agreed we might move the launch, it's not decided yet."
    assert extract_structured_report(transcript)["decisions"] == []


# ─── Tasks ─────────────────────────────────────────────────────────────────

def test_task_captures_assignee_and_iso_due_date():
    tasks = extract_structured_report(TRANSCRIPT)["tasks"]
    task = next(t for t in tasks if "migration plan" in t["title"].lower())

    assert task["assignee"] == "Priya"
    assert task["due_date"] == "2026-10-02"  # Friday after 2026-09-28
    assert task["description"]


def test_task_without_stated_owner_or_date_keeps_nulls():
    transcript = "Dana: I will prepare the board deck."
    task = extract_structured_report(transcript)["tasks"][0]

    assert task["assignee"] == "Dana"
    assert task["due_date"] is None


def test_collective_assignment_never_becomes_an_owner():
    transcript = "Meeting: Ops Sync\nDate: 2026-09-28\nDana: We should ship the report tomorrow."
    tasks = extract_structured_report(transcript)["tasks"]

    # The commitment is kept, but no individual is invented for it.
    assert len(tasks) == 1
    assert tasks[0]["assignee"] is None
    # "tomorrow" resolves against the meeting date stated in the transcript.
    assert tasks[0]["due_date"] == "2026-09-29"


def test_stated_deadline_without_a_connector_is_still_captured():
    transcript = "Meeting: Ops Sync\nDate: 2026-09-28\nPriya: I'll file the report tomorrow."
    task = extract_structured_report(transcript)["tasks"][0]
    assert task["due_date"] == "2026-09-29"


def test_unresolvable_deadline_becomes_null():
    transcript = "Sarah: Priya will send the contract by the end of the phase."
    task = extract_structured_report(transcript)["tasks"][0]
    assert task["due_date"] is None


# ─── Blockers ──────────────────────────────────────────────────────────────

def test_blockers_and_risks_are_captured():
    issues = [b["issue"].lower() for b in extract_structured_report(TRANSCRIPT)["blockers"]]
    assert any("legal sign-off" in i for i in issues)
    assert any("staging environment" in i for i in issues)


def test_negated_risk_is_not_a_blocker():
    transcript = "Sarah: There are no blockers, we are not at risk on this."
    assert extract_structured_report(transcript)["blockers"] == []


def test_open_question_is_recorded_as_a_blocker():
    transcript = "Sarah: Are we still targeting the European launch this year?"
    blockers = extract_structured_report(transcript)["blockers"]
    assert len(blockers) == 1
    assert "European" in blockers[0]["issue"]


def test_logistics_questions_are_ignored():
    transcript = "Sarah: Can everyone hear me okay?"
    assert extract_structured_report(transcript)["blockers"] == []


# ─── API ───────────────────────────────────────────────────────────────────

def test_typed_transcript_endpoint(client):
    res = client.post("/transcripts/analyze", json={"transcript": TRANSCRIPT})
    assert res.status_code == 200

    body = res.json()
    assert set(body) == CONTRACT_KEYS
    assert body["meeting_title"] == "Q3 Pricing Launch Sync"
    assert body["tasks"]


def test_uploaded_txt_file_endpoint(client):
    payload = io.BytesIO(TRANSCRIPT.encode("utf-8"))
    res = client.post(
        "/transcripts/analyze/file",
        files={"file": ("sync.txt", payload, "text/plain")},
    )
    assert res.status_code == 200
    assert res.json()["decisions"]


def test_uploaded_file_endpoint_rejects_unsupported_type(client):
    payload = io.BytesIO(b"%PDF-1.4")
    res = client.post(
        "/transcripts/analyze/file",
        files={"file": ("deck.pdf", payload, "application/pdf")},
    )
    assert res.status_code == 400


def test_typed_and_uploaded_transcripts_agree(client):
    typed = client.post("/transcripts/analyze", json={"transcript": TRANSCRIPT}).json()
    uploaded = client.post(
        "/transcripts/analyze/file",
        files={"file": ("sync.txt", io.BytesIO(TRANSCRIPT.encode()), "text/plain")},
    ).json()

    assert json.dumps(typed, sort_keys=True) == json.dumps(uploaded, sort_keys=True)