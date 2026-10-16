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


def test_build_site_payload_includes_pending_and_scored():
    scored = [
        {
            "match_id": "2026-10-15_men_a_b",
            "prediction": {
                "competition": "men",
                "home_team": "A",
                "away_team": "B",
                "kickoff_utc": "2026-10-15T09:00:00Z",
                "made_at": "2026-10-14T12:00:00Z",
                "home_win_prob": 0.6,
                "away_win_prob": 0.4,
                "predicted_margin": 8,
                "predicted_winner": "home",
                "reasoning": "form",
            },
            "result": {"home_score": 20, "away_score": 10, "locked": True, "source": "test"},
            "scored": {
                "hit": 1.0,
                "brier": 0.16,
                "margin_error": 2,
                "ranking_hit": 1.0,
                "pred_side": "home",
            },
        }
    ]
    pending = [
        {
            "match_id": "2026-10-16_women_c_d",
            "prediction": {
                "competition": "women",
                "home_team": "C",
                "away_team": "D",
                "kickoff_utc": "2026-10-16T09:00:00Z",
                "made_at": "2026-10-15T12:00:00Z",
                "home_win_prob": 0.55,
                "away_win_prob": 0.45,
                "predicted_margin": 4,
                "predicted_winner": "home",
                "reasoning": "edge",
            },
        }
    ]
    payload = run.scoreboard_site.build_site_payload(
        updated="2026-10-16T00:00:00Z",
        scored_rows=scored,
        pending_rows=pending,
        overall=run.summarize_rows(scored),
        men=run.summarize_rows(scored),
        women=run.scoreboard_site.empty_stats(),
    )
    assert payload["summaries"]["overall"]["count"] == 1
    assert len(payload["matches"]) == 2
    assert payload["matches"][0]["status"] == "scored"
    assert payload["matches"][1]["status"] == "pending"
    html = run.scoreboard_site.render_index_html(payload)
    assert "RLWC" in html
    assert '"home_team": "C"' in html
    assert '"away_team": "D"' in html


def test_build_site_payload_includes_scheduled_without_prediction():
    scheduled = [
        {
            "match_id": "2026-10-17_men_england_tonga",
            "competition": "men",
            "home_team": "England",
            "away_team": "Tonga",
            "kickoff_utc": "2026-10-17T09:05:00Z",
            "venue": "HBF Park, Perth",
            "stage": "pool",
            "pool": "B",
        }
    ]
    payload = run.scoreboard_site.build_site_payload(
        updated="2026-10-05T00:00:00Z",
        scored_rows=[],
        pending_rows=[],
        overall=run.scoreboard_site.empty_stats(),
        men=run.scoreboard_site.empty_stats(),
        women=run.scoreboard_site.empty_stats(),
        scheduled_rows=scheduled,
    )
    assert len(payload["matches"]) == 1
    match = payload["matches"][0]
    assert match["status"] == "scheduled"
    assert match["prediction"] is None
    assert match["home_team"] == "England"
    html = run.scoreboard_site.render_index_html(payload)
    assert "No prediction yet" in html
    assert "England" in html
    assert "formatKickoffAedt" in html
    assert "Australia/Sydney" in html


def test_load_scheduled_fixtures_has_men_and_women_pools():
    fixtures = run.load_scheduled_fixtures()
    assert len(fixtures) >= 20
    comps = {row["competition"] for row in fixtures}
    assert comps == {"men", "women"}
    assert all(row["stage"] == "pool" for row in fixtures)
    assert all(row.get("match_id") for row in fixtures)
    # Prediction rows must win over scheduled duplicates.
    pending = [
        {
            "match_id": fixtures[0]["match_id"],
            "prediction": {
                "competition": fixtures[0]["competition"],
                "home_team": fixtures[0]["home_team"],
                "away_team": fixtures[0]["away_team"],
                "kickoff_utc": fixtures[0]["kickoff_utc"],
                "made_at": "2026-10-01T00:00:00Z",
                "home_win_prob": 0.6,
                "away_win_prob": 0.4,
                "predicted_margin": 6,
                "predicted_winner": "home",
                "reasoning": "test",
            },
        }
    ]
    payload = run.scoreboard_site.build_site_payload(
        updated="2026-10-05T00:00:00Z",
        scored_rows=[],
        pending_rows=pending,
        overall=run.scoreboard_site.empty_stats(),
        men=run.scoreboard_site.empty_stats(),
        women=run.scoreboard_site.empty_stats(),
        scheduled_rows=fixtures,
    )
    by_id = {m["match_id"]: m for m in payload["matches"]}
    assert by_id[fixtures[0]["match_id"]]["status"] == "pending"
    assert len(payload["matches"]) == len(fixtures)


def test_dedupe_pending_predictions_keeps_one_per_pairing():
    fixtures = [
        {
            "match_id": "2026-10-16_women_australia_samoa",
            "competition": "women",
            "home_team": "Australia",
            "away_team": "Samoa",
            "kickoff_utc": "2026-10-16T09:05:00Z",
            "venue": "CommBank Stadium, Sydney",
            "stage": "pool",
        }
    ]
    pending = [
        {
            "match_id": "2026-10-15_women_australia_samoa",
            "prediction": {
                "competition": "women",
                "home_team": "Australia",
                "away_team": "Samoa",
                "kickoff_utc": "2026-10-15T15:05:00Z",
                "made_at": "2026-10-14T22:00:00Z",
                "home_win_prob": 0.9,
                "away_win_prob": 0.1,
            },
        },
        {
            "match_id": "2026-10-16_women_australia_samoa",
            "prediction": {
                "competition": "women",
                "home_team": "Australia",
                "away_team": "Samoa",
                "kickoff_utc": "2026-10-16T09:05:00Z",
                "made_at": "2026-10-15T22:00:00Z",
                "home_win_prob": 0.98,
                "away_win_prob": 0.02,
            },
        },
    ]
    deduped = run.dedupe_pending_predictions(pending, fixtures)
    assert len(deduped) == 1
    assert deduped[0]["match_id"] == "2026-10-16_women_australia_samoa"
    assert deduped[0]["prediction"]["kickoff_utc"] == "2026-10-16T09:05:00Z"
    assert deduped[0]["prediction"]["home_win_prob"] == 0.98


def test_women_fixtures_include_canonical_opener():
    fixtures = run.load_scheduled_fixtures()
    women = [row for row in fixtures if row["competition"] == "women"]
    opener = next(
        row
        for row in women
        if row["home_team"] == "Australia" and row["away_team"] == "Samoa"
    )
    assert opener["kickoff_utc"] == "2026-10-16T09:05:00Z"
    assert opener["match_id"] == "2026-10-16_women_australia_samoa"
    # No duplicate Australia-Samoa rows in curated fixtures.
    aus_samoa = [
        row
        for row in women
        if {row["home_team"], row["away_team"]} == {"Australia", "Samoa"}
    ]
    assert len(aus_samoa) == 1
