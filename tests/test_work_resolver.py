"""Tests for cross-meeting calendar work resolution."""

from app.services.work_resolver import detect_work_resolutions


def test_detect_work_resolutions_from_decision():
    active_events = [
        {
            "id": 1,
            "title": "Draft legal sign-off for release",
            "description": "Action item from meeting 1",
            "owner": "Priya",
            "date": "2026-10-15",
            "priority": "HIGH"
        },
        {
            "id": 2,
            "title": "Configure staging servers",
            "description": "Action item from meeting 1",
            "owner": "Marcus",
            "date": "2026-10-16",
            "priority": "MEDIUM"
        }
    ]

    new_transcript = """Meeting: Follow-up Sync
Priya: Good news everyone, the legal sign-off has been approved and completed.
Marcus: Staging is still pending.
"""

    decisions = [
        {"decision": "Legal sign-off is completed", "context": "Priya confirmed approval"}
    ]

    resolutions = detect_work_resolutions(
        active_events=active_events,
        meeting_title="Follow-up Sync",
        decisions=decisions,
        transcript=new_transcript
    )

    assert len(resolutions) == 1
    assert resolutions[0]["event_id"] == 1
    assert resolutions[0]["status"] == "RESOLVED"
    assert "Follow-up Sync" in resolutions[0]["reason"]
    assert "legal sign-off" in resolutions[0]["reason"].lower()


def test_detect_work_cancelled():
    active_events = [
        {
            "id": 5,
            "title": "Build discount tier calculator",
            "description": "Action item from meeting 1",
            "owner": "Sarah",
            "date": "2026-10-20",
            "priority": "LOW"
        }
    ]

    new_transcript = """Meeting: Strategy Pivot
Sarah: We decided the discount tier calculator is cancelled and no longer needed.
"""

    resolutions = detect_work_resolutions(
        active_events=active_events,
        meeting_title="Strategy Pivot",
        decisions=[],
        transcript=new_transcript
    )

    assert len(resolutions) == 1
    assert resolutions[0]["event_id"] == 5
    assert resolutions[0]["status"] == "CANCELLED"
    assert "Strategy Pivot" in resolutions[0]["reason"]
