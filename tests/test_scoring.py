"""Unit tests for scoring helpers (no live Gemini calls)."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

run = importlib.import_module("run")


def test_normalize_probs():
    assert run.normalize_probs(0.7, 0.3) == (0.7, 0.3)
    home, away = run.normalize_probs(2, 2)
    assert abs(home - 0.5) < 1e-9
    assert abs(away - 0.5) < 1e-9
    home, away = run.normalize_probs(0, 0)
    assert home == 0.5 and away == 0.5
    home, away = run.normalize_probs(None, None)
    assert home == 0.5 and away == 0.5


def test_extract_json_from_fence():
    text = 'Here you go:\n```json\n{"matches": []}\n```\n'
    assert run.extract_json(text) == {"matches": []}


def test_match_id_includes_competition():
    men = run.match_id("2026-10-15T09:00:00Z", "men", "Australia", "New Zealand")
    women = run.match_id("2026-10-16T09:00:00Z", "women", "Australia", "New Zealand")
    assert men == "2026-10-15_men_australia_new-zealand"
    assert women == "2026-10-16_women_australia_new-zealand"
    assert men != women


def test_normalize_competition():
    assert run.normalize_competition("men") == "men"
    assert run.normalize_competition("Women's") == "women"
    assert run.normalize_competition("mens") == "men"
    assert run.normalize_competition("wheelchair") is None


def test_kickoff_still_upcoming_hard_cutoff():
    now = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
    assert run.kickoff_still_upcoming("2026-10-15T09:05:00Z", now) is True
    assert run.kickoff_still_upcoming("2026-10-15T09:00:00Z", now) is False
    assert run.kickoff_still_upcoming("2026-10-15T08:50:00Z", now) is False


def test_score_row_home_win():
    prediction = {
        "home_win_prob": 0.7,
        "away_win_prob": 0.3,
        "predicted_margin": 10,
        "predicted_winner": "home",
        "home_rank": 1,
        "away_rank": 5,
    }
    result = {"home_score": 24, "away_score": 12}
    scored = run.score_row(prediction, result)
    assert scored["actual_winner"] == "home"
    assert scored["hit"] == 1.0
    assert abs(scored["brier"] - (0.3**2)) < 1e-9
    assert scored["margin_error"] == 2
    assert scored["ranking_hit"] == 1.0


def test_score_row_upset():
    prediction = {
        "home_win_prob": 0.8,
        "away_win_prob": 0.2,
        "predicted_margin": 14,
        "predicted_winner": "home",
        "home_rank": 2,
        "away_rank": 8,
    }
    result = {"home_score": 10, "away_score": 18}
    scored = run.score_row(prediction, result)
    assert scored["actual_winner"] == "away"
    assert scored["hit"] == 0.0
    assert abs(scored["brier"] - (0.8**2)) < 1e-9
    assert scored["ranking_hit"] == 0.0
    # Wrong winner: signed margin error is 14 - (-8) = 22
    assert scored["margin_error"] == 22


def test_score_row_uses_probs_not_stated_winner():
    prediction = {
        "home_win_prob": 0.2,
        "away_win_prob": 0.8,
        "predicted_margin": 8,
        "predicted_winner": "home",  # inconsistent with probs
        "home_rank": 5,
        "away_rank": 1,
    }
    result = {"home_score": 6, "away_score": 20}
    scored = run.score_row(prediction, result)
    assert scored["pred_side"] == "away"
    assert scored["hit"] == 1.0


def test_score_row_draw_half():
    prediction = {
        "home_win_prob": 0.55,
        "away_win_prob": 0.45,
        "predicted_margin": 2,
        "predicted_winner": "home",
        "home_rank": 3,
        "away_rank": 4,
    }
    result = {"home_score": 16, "away_score": 16}
    scored = run.score_row(prediction, result)
    assert scored["actual_winner"] == "draw"
    assert scored["hit"] == 0.5
    assert scored["ranking_hit"] == 0.5
    expected_brier = 0.5 * ((0.55 - 0.5) ** 2 + (0.45 - 0.5) ** 2)
    assert abs(scored["brier"] - expected_brier) < 1e-9


def test_prediction_before_kickoff_picks_latest_eligible():
    versions = [
        {"made_at": "2026-10-14T01:00:00Z", "home_win_prob": 0.4},
        {"made_at": "2026-10-14T10:00:00Z", "home_win_prob": 0.6},
        {"made_at": "2026-10-15T12:00:00Z", "home_win_prob": 0.9},
    ]
    kickoff = run.parse_iso("2026-10-15T09:00:00Z")
    chosen = run.prediction_before_kickoff(versions, kickoff)
    assert chosen is not None
    assert chosen["home_win_prob"] == 0.6


def test_merge_result_locks_on_second_agreeing_lookup():
    kickoff = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
    now = kickoff + timedelta(hours=3)
    first = {
        "home_score": 24,
        "away_score": 12,
        "verified_count": 1,
        "locked": False,
        "source": "a",
    }
    second = {
        "home_score": 24,
        "away_score": 12,
        "verified_count": 1,
        "locked": False,
        "source": "b",
    }
    merged = run.merge_result(first, second, kickoff, now)
    assert merged is not None
    assert merged["verified_count"] == 2
    assert merged["locked"] is True


def test_merge_result_resets_on_mismatch():
    kickoff = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
    now = kickoff + timedelta(hours=3)
    first = {
        "home_score": 24,
        "away_score": 12,
        "verified_count": 1,
        "locked": False,
        "source": "a",
        "recorded_at": "2026-10-15T11:00:00Z",
    }
    second = {
        "home_score": 20,
        "away_score": 18,
        "verified_count": 1,
        "locked": False,
        "source": "b",
    }
    merged = run.merge_result(first, second, kickoff, now)
    assert merged is not None
    assert merged["home_score"] == 20
    assert merged["verified_count"] == 1
    assert merged["locked"] is False
    assert merged["previous"]["home_score"] == 24


def _scored_row(competition: str, hit: float, brier: float, match_id: str) -> dict:
    return {
        "match_id": match_id,
        "prediction": {
            "competition": competition,
            "home_team": "A",
            "away_team": "B",
            "home_win_prob": 0.6,
            "away_win_prob": 0.4,
            "kickoff_utc": "2026-10-16T09:00:00Z",
        },
        "result": {"home_score": 20, "away_score": 10, "locked": True},
        "scored": {
            "actual_winner": "home",
            "hit": hit,
            "brier": brier,
            "margin_error": 4,
            "ranking_hit": 1.0,
            "pred_side": "home",
        },
    }


def test_group_rows_by_competition():
    rows = [
        _scored_row("men", 1.0, 0.16, "2026-10-15_men_a_b"),
        _scored_row("women", 0.0, 0.36, "2026-10-16_women_a_b"),
        _scored_row("men", 1.0, 0.09, "2026-10-17_men_c_d"),
    ]
    grouped = run.group_rows_by_competition(rows)
    assert len(grouped["men"]) == 2
    assert len(grouped["women"]) == 1


def test_summarize_rows_overall_and_split():
    rows = [
        _scored_row("men", 1.0, 0.16, "2026-10-15_men_a_b"),
        _scored_row("women", 0.0, 0.36, "2026-10-16_women_a_b"),
    ]
    overall = run.summarize_rows(rows)
    men = run.summarize_rows(run.group_rows_by_competition(rows)["men"])
    women = run.summarize_rows(run.group_rows_by_competition(rows)["women"])
    assert overall["count"] == 2
    assert abs(overall["hit_rate"] - 0.5) < 1e-9
    assert men["count"] == 1 and men["hit_rate"] == 1.0
    assert women["count"] == 1 and women["hit_rate"] == 0.0
