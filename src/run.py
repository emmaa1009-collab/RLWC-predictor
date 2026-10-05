#!/usr/bin/env python3
"""RLWC 2026 predictor: discover fixtures, predict, record, and score via Gemini."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
PREDICTIONS_DIR = ROOT / "data" / "predictions"
RESULTS_DIR = ROOT / "data" / "results"
SCOREBOARD_PATH = ROOT / "SCOREBOARD.md"
BASELINE_ODDS_PATH = ROOT / "data" / "baseline_odds.json"

# "half" scores draws as 0.5 for hit-rate; "exclude" drops draws from hit-rate.
DRAW_HANDLING = os.environ.get("DRAW_HANDLING", "half")

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in {"1", "true", "yes"}
LOOKAHEAD_HOURS = 36
# Never predict a match once kickoff has passed (avoids live-score leakage via search).
PREDICT_BUFFER_MINUTES = 1
# Re-check unlocked results until two agreeing lookups, or until this long after kickoff.
RESULT_LOCK_AFTER = timedelta(hours=24)
RESULT_AGREE_TO_LOCK = 2

SYSTEM_RULES = """
You are forecasting the 2026 Men's Rugby League World Cup (15 Oct–15 Nov 2026,
hosted in Australia, New Zealand and Papua New Guinea).

Rules:
- Use Google Search for current fixtures, form, injuries, squads, rankings, venue,
  and head-to-head. Prefer official / reputable rugby league sources.
- Never invent final scores for unfinished matches.
- Respond with JSON only. No markdown fences, no commentary outside JSON.
""".strip()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    cleaned = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def slugify(name: str) -> str:
    text = name.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "team"


def match_id(kickoff_utc: str, home: str, away: str) -> str:
    day = parse_iso(kickoff_utc).strftime("%Y-%m-%d")
    return f"{day}_{slugify(home)}_{slugify(away)}"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if DRY_RUN:
        print(f"[dry_run] would write {path.relative_to(ROOT)}")
        print(json.dumps(data, indent=2))
        return
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def extract_json(text: str) -> Any:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start_obj = cleaned.find("{")
        start_arr = cleaned.find("[")
        starts = [i for i in (start_obj, start_arr) if i >= 0]
        if not starts:
            raise
        start = min(starts)
        end_obj = cleaned.rfind("}")
        end_arr = cleaned.rfind("]")
        end = max(end_obj, end_arr)
        if end <= start:
            raise
        return json.loads(cleaned[start : end + 1])


def require_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print(
            "GEMINI_API_KEY is not set. Add it as a GitHub Actions secret "
            "or export it locally before running.",
            file=sys.stderr,
        )
        sys.exit(1)
    return key


def gemini_json(client: genai.Client, prompt: str) -> Any:
    config = types.GenerateContentConfig(
        temperature=0.2,
        tools=[types.Tool(google_search=types.GoogleSearch())],
        system_instruction=SYSTEM_RULES,
    )
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=config,
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned an empty response")
    print("--- gemini response ---")
    print(text[:4000])
    print("--- end response ---")
    return extract_json(text)


def coerce_float(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_probs(home: Any, away: Any) -> tuple[float, float]:
    home_f = coerce_float(home, 0.5)
    away_f = coerce_float(away, 0.5)
    home_f = max(0.0, min(1.0, home_f))
    away_f = max(0.0, min(1.0, away_f))
    total = home_f + away_f
    if total <= 0:
        return 0.5, 0.5
    return home_f / total, away_f / total


def pick_from_probs(home_p: float, away_p: float) -> str:
    """Side implied by probabilities (>50%). Exact 50/50 returns 'tie'."""
    if home_p > away_p:
        return "home"
    if away_p > home_p:
        return "away"
    return "tie"


def kickoff_still_upcoming(kickoff_utc: str, now: datetime) -> bool:
    return parse_iso(kickoff_utc) > now + timedelta(minutes=PREDICT_BUFFER_MINUTES)


def discover_fixtures(client: genai.Client, now: datetime) -> list[dict[str, Any]]:
    until = now + timedelta(hours=LOOKAHEAD_HOURS)
    earliest = now + timedelta(minutes=PREDICT_BUFFER_MINUTES)
    prompt = f"""
Search for Men's Rugby League World Cup 2026 fixtures with kickoff between
{iso_z(earliest)} and {iso_z(until)} (UTC), inclusive.

Return a JSON object:
{{
  "matches": [
    {{
      "home_team": "string",
      "away_team": "string",
      "kickoff_utc": "YYYY-MM-DDTHH:MM:SSZ",
      "venue": "string or empty",
      "stage": "pool" or "knockout"
    }}
  ]
}}

If none are found, return {{"matches": []}}.
Use official team names. Only include men's tournament matches.
Do not include matches that have already kicked off.
""".strip()
    payload = gemini_json(client, prompt)
    matches = payload.get("matches", []) if isinstance(payload, dict) else []
    cleaned: list[dict[str, Any]] = []
    for raw in matches:
        try:
            home = str(raw["home_team"]).strip()
            away = str(raw["away_team"]).strip()
            kickoff = iso_z(parse_iso(str(raw["kickoff_utc"])))
            stage = str(raw.get("stage", "pool")).strip().lower()
            if stage not in {"pool", "knockout"}:
                stage = "pool"
            if not home or not away:
                continue
            kickoff_dt = parse_iso(kickoff)
            # Hard cutoff: never keep a fixture that has already started.
            if kickoff_dt <= now + timedelta(minutes=PREDICT_BUFFER_MINUTES):
                continue
            if kickoff_dt > until + timedelta(hours=1):
                continue
            cleaned.append(
                {
                    "home_team": home,
                    "away_team": away,
                    "kickoff_utc": kickoff,
                    "venue": str(raw.get("venue") or "").strip(),
                    "stage": stage,
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            print(f"Skipping malformed fixture: {raw!r} ({exc})")
    return cleaned


def predict_one(client: genai.Client, match: dict[str, Any], now: datetime) -> dict[str, Any]:
    if not kickoff_still_upcoming(match["kickoff_utc"], now):
        raise RuntimeError(f"Kickoff has passed for {match['home_team']} vs {match['away_team']}")

    prompt = f"""
Research this upcoming Men's RLWC 2026 match and produce a probability forecast.

Match:
- Home: {match['home_team']}
- Away: {match['away_team']}
- Kickoff UTC: {match['kickoff_utc']}
- Venue: {match.get('venue') or 'unknown'}
- Stage: {match['stage']}

Consider recent form, squad/injury news, world rankings, venue/travel, and head-to-head.
Do not use any information from after kickoff. Do not report a final score.
If you can see live or final scores, refuse and return:
{{"refuse": true, "reason": "match already started or finished"}}

Return JSON:
{{
  "home_win_prob": 0.0_to_1.0,
  "away_win_prob": 0.0_to_1.0,
  "predicted_margin": integer_points_absolute_winning_margin,
  "predicted_winner": "home" or "away",
  "home_rank": integer_or_null,
  "away_rank": integer_or_null,
  "reasoning": "2-4 sentences citing the key evidence"
}}

home_win_prob + away_win_prob must equal 1. predicted_margin is the absolute
expected winning margin in points (always >= 0).
Current UTC time for the audit trail: {iso_z(now)}
""".strip()
    raw = gemini_json(client, prompt)
    if not isinstance(raw, dict):
        raise RuntimeError(f"Expected JSON object, got {type(raw).__name__}")
    if raw.get("refuse"):
        raise RuntimeError(f"Model refused prediction: {raw.get('reason', 'unknown')}")

    home_p, away_p = normalize_probs(raw.get("home_win_prob"), raw.get("away_win_prob"))
    winner = pick_from_probs(home_p, away_p)
    if winner == "tie":
        stated = str(raw.get("predicted_winner", "")).strip().lower()
        winner = stated if stated in {"home", "away"} else "home"

    margin = abs(int(round(coerce_float(raw.get("predicted_margin"), 0.0))))
    home_rank = raw.get("home_rank")
    away_rank = raw.get("away_rank")
    try:
        home_rank = int(home_rank) if home_rank is not None else None
    except (TypeError, ValueError):
        home_rank = None
    try:
        away_rank = int(away_rank) if away_rank is not None else None
    except (TypeError, ValueError):
        away_rank = None

    # Stamp made_at at write-time so a slow run cannot back-date past kickoff.
    made_at = utc_now()
    if not kickoff_still_upcoming(match["kickoff_utc"], made_at):
        raise RuntimeError("Kickoff passed while researching; discarding prediction")

    return {
        "made_at": iso_z(made_at),
        "kickoff_utc": match["kickoff_utc"],
        "home_team": match["home_team"],
        "away_team": match["away_team"],
        "venue": match.get("venue", ""),
        "stage": match["stage"],
        "home_win_prob": round(home_p, 4),
        "away_win_prob": round(away_p, 4),
        "predicted_margin": margin,
        "predicted_winner": winner,
        "home_rank": home_rank,
        "away_rank": away_rank,
        "reasoning": str(raw.get("reasoning") or "").strip(),
        "model": MODEL,
    }


def materially_changed(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    keys = (
        "home_win_prob",
        "away_win_prob",
        "predicted_margin",
        "predicted_winner",
        "home_rank",
        "away_rank",
        "reasoning",
    )
    for key in keys:
        if previous.get(key) != current.get(key):
            return True
    return False


def append_prediction(match: dict[str, Any], version: dict[str, Any]) -> Path:
    mid = match_id(match["kickoff_utc"], match["home_team"], match["away_team"])
    path = PREDICTIONS_DIR / f"{mid}.json"
    existing = load_json(path, [])
    if not isinstance(existing, list):
        existing = []
    if existing and not materially_changed(existing[-1], version):
        print(f"No material change for {mid}; keeping existing versions.")
        return path
    existing.append(version)
    write_json(path, existing)
    return path


def prediction_before_kickoff(versions: list[dict[str, Any]], kickoff: datetime) -> dict[str, Any] | None:
    eligible = []
    for version in versions:
        try:
            made_at = parse_iso(str(version["made_at"]))
        except (KeyError, ValueError):
            continue
        if made_at <= kickoff:
            eligible.append((made_at, version))
    if not eligible:
        return None
    eligible.sort(key=lambda item: item[0])
    return eligible[-1][1]


def list_prediction_files() -> list[Path]:
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(PREDICTIONS_DIR.glob("*.json"))


def lookup_result(client: genai.Client, meta: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    prompt = f"""
Has this Men's RLWC 2026 match finished?

- Home: {meta['home_team']}
- Away: {meta['away_team']}
- Kickoff UTC: {meta['kickoff_utc']}

Current UTC time: {iso_z(now)}

If the match has not finished (or you cannot verify a final score), return:
{{"finished": false}}

If finished, return:
{{
  "finished": true,
  "home_score": integer,
  "away_score": integer,
  "source": "short source name or URL"
}}

Only mark finished when you can cite a final full-time score from a reputable source.
""".strip()
    raw = gemini_json(client, prompt)
    if not isinstance(raw, dict) or not raw.get("finished"):
        return None
    try:
        home_score = int(raw["home_score"])
        away_score = int(raw["away_score"])
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "home_team": meta["home_team"],
        "away_team": meta["away_team"],
        "kickoff_utc": meta["kickoff_utc"],
        "home_score": home_score,
        "away_score": away_score,
        "recorded_at": iso_z(now),
        "source": str(raw.get("source") or "").strip(),
        "model": MODEL,
        "verified_count": 1,
        "locked": False,
    }


def merge_result(
    existing: dict[str, Any] | None,
    looked_up: dict[str, Any] | None,
    kickoff: datetime,
    now: datetime,
) -> dict[str, Any] | None:
    """Keep results provisional until confirmed twice or past RESULT_LOCK_AFTER."""
    if existing and existing.get("locked"):
        return existing

    if looked_up is None:
        if existing is None:
            return None
        # Age out provisional results that never get a second confirm after the lock window.
        if now >= kickoff + RESULT_LOCK_AFTER and int(existing.get("verified_count", 1)) >= 1:
            existing = dict(existing)
            existing["locked"] = True
            existing["locked_at"] = iso_z(now)
            existing["lock_reason"] = "age"
            return existing
        return existing

    if existing is None:
        return looked_up

    same = (
        int(existing["home_score"]) == int(looked_up["home_score"])
        and int(existing["away_score"]) == int(looked_up["away_score"])
    )
    merged = dict(existing)
    if same:
        merged["verified_count"] = int(existing.get("verified_count", 1)) + 1
        merged["source"] = looked_up.get("source") or existing.get("source", "")
        merged["last_checked_at"] = iso_z(now)
        if merged["verified_count"] >= RESULT_AGREE_TO_LOCK or now >= kickoff + RESULT_LOCK_AFTER:
            merged["locked"] = True
            merged["locked_at"] = iso_z(now)
            merged["lock_reason"] = "confirmed" if merged["verified_count"] >= RESULT_AGREE_TO_LOCK else "age"
        return merged

    print(
        f"Result mismatch for {existing.get('home_team')} vs {existing.get('away_team')}: "
        f"{existing['home_score']}-{existing['away_score']} -> "
        f"{looked_up['home_score']}-{looked_up['away_score']}; keeping newer provisional score."
    )
    looked_up = dict(looked_up)
    looked_up["verified_count"] = 1
    looked_up["locked"] = False
    looked_up["previous"] = {
        "home_score": existing["home_score"],
        "away_score": existing["away_score"],
        "source": existing.get("source", ""),
        "recorded_at": existing.get("recorded_at"),
    }
    return looked_up


def score_row(
    prediction: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    home_score = int(result["home_score"])
    away_score = int(result["away_score"])
    actual_margin = abs(home_score - away_score)
    draw = home_score == away_score

    home_p, away_p = normalize_probs(prediction.get("home_win_prob"), prediction.get("away_win_prob"))
    # Hit rate follows README: side given >50% probability.
    pred_winner = pick_from_probs(home_p, away_p)

    if draw:
        hit: float | None
        if DRAW_HANDLING == "exclude":
            hit = None
        else:
            hit = 0.5
        # Score vs a 0.5/0.5 target when the match draws (no explicit draw probability).
        brier = 0.5 * ((home_p - 0.5) ** 2 + (away_p - 0.5) ** 2)
        actual_winner = "draw"
    else:
        actual_winner = "home" if home_score > away_score else "away"
        p_actual = home_p if actual_winner == "home" else away_p
        if pred_winner == "tie":
            hit = 0.5
        else:
            hit = 1.0 if pred_winner == actual_winner else 0.0
        brier = (1.0 - p_actual) ** 2

    ranking_pick = None
    home_rank = prediction.get("home_rank")
    away_rank = prediction.get("away_rank")
    if isinstance(home_rank, int) and isinstance(away_rank, int) and home_rank != away_rank:
        ranking_pick = "home" if home_rank < away_rank else "away"

    ranking_hit: float | None
    if draw:
        ranking_hit = None if DRAW_HANDLING == "exclude" else 0.5
    elif ranking_pick is None:
        ranking_hit = None
    else:
        ranking_hit = 1.0 if ranking_pick == actual_winner else 0.0

    # Signed margins so a wrong-winner same-abs-margin is not scored as perfect.
    stated_winner = prediction.get("predicted_winner")
    if stated_winner not in {"home", "away"}:
        stated_winner = "home" if pred_winner != "away" else "away"
    pred_margin = abs(int(round(coerce_float(prediction.get("predicted_margin"), 0.0))))
    pred_signed = pred_margin if stated_winner == "home" else -pred_margin
    actual_signed = home_score - away_score
    margin_error = abs(pred_signed - actual_signed)

    return {
        "actual_winner": actual_winner,
        "actual_margin": actual_margin,
        "hit": hit,
        "brier": brier,
        "margin_error": margin_error,
        "ranking_hit": ranking_hit,
        "coin_flip_brier": 0.25,
        "pred_side": pred_winner,
    }


def mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def format_num(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def load_market_baseline() -> dict[str, dict[str, float]]:
    data = load_json(BASELINE_ODDS_PATH, {})
    return data if isinstance(data, dict) else {}


def rebuild_scoreboard(rows: list[dict[str, Any]]) -> None:
    market = load_market_baseline()
    agent_hits: list[float] = []
    agent_briers: list[float] = []
    margin_errors: list[float] = []
    ranking_hits: list[float] = []
    market_hits: list[float] = []
    market_briers: list[float] = []

    lines = [
        "# SCOREBOARD",
        "",
        f"Updated: {iso_z(utc_now())}",
        "",
        "| Match | Score | Agent pick | Hit | Brier | Margin err | Rank baseline | Locked |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for row in rows:
        pred = row["prediction"]
        result = row["result"]
        scored = row["scored"]
        label = f"{pred['home_team']} vs {pred['away_team']}"
        score = f"{result['home_score']}-{result['away_score']}"
        side = scored.get("pred_side") or pick_from_probs(
            float(pred["home_win_prob"]), float(pred["away_win_prob"])
        )
        if side == "home":
            pick = pred["home_team"]
        elif side == "away":
            pick = pred["away_team"]
        else:
            pick = "50/50"
        hit = scored["hit"]
        hit_cell = "n/a" if hit is None else ("Y" if hit == 1.0 else ("½" if hit == 0.5 else "N"))
        rank_hit = scored["ranking_hit"]
        rank_cell = "n/a" if rank_hit is None else ("Y" if rank_hit == 1.0 else ("½" if rank_hit == 0.5 else "N"))
        locked = "Y" if result.get("locked") else "N"
        lines.append(
            f"| {label} | {score} | {pick} ({pred['home_win_prob']:.0%}) | {hit_cell} | "
            f"{scored['brier']:.3f} | {scored['margin_error']} | {rank_cell} | {locked} |"
        )

        if scored["hit"] is not None:
            agent_hits.append(float(scored["hit"]))
        agent_briers.append(float(scored["brier"]))
        margin_errors.append(float(scored["margin_error"]))
        if scored["ranking_hit"] is not None:
            ranking_hits.append(float(scored["ranking_hit"]))

        mid = row["match_id"]
        odds = market.get(mid)
        if odds and scored["actual_winner"] != "draw":
            mh = float(odds.get("home_win_prob", 0.5))
            ma = float(odds.get("away_win_prob", 0.5))
            mh, ma = normalize_probs(mh, ma)
            market_pick = pick_from_probs(mh, ma)
            if market_pick == "tie":
                market_hits.append(0.5)
            else:
                market_hits.append(1.0 if market_pick == scored["actual_winner"] else 0.0)
            p_act = mh if scored["actual_winner"] == "home" else ma
            market_briers.append((1.0 - p_act) ** 2)

    lines.extend(
        [
            "",
            "## Summary",
            "",
            "| Metric | Agent | Ranking baseline | Coin flip | Market odds |",
            "|---|---|---|---|---|",
            f"| Hit rate | {format_pct(mean(agent_hits))} | {format_pct(mean(ranking_hits))} | 50.0% | {format_pct(mean(market_hits))} |",
            f"| Brier (lower better) | {format_num(mean(agent_briers))} | n/a | 0.250 | {format_num(mean(market_briers))} |",
            f"| Mean abs margin error | {format_num(mean(margin_errors), 2)} | n/a | n/a | n/a |",
            "",
            f"Matches scored: {len(rows)}. Draw handling: `{DRAW_HANDLING}`.",
            "Results stay provisional until two agreeing lookups or 24h after kickoff.",
            "",
            "Market odds come from `data/baseline_odds.json` when present (optional, manual).",
            "",
        ]
    )

    content = "\n".join(lines)
    if DRY_RUN:
        print("[dry_run] would write SCOREBOARD.md")
        print(content)
        return
    SCOREBOARD_PATH.write_text(content, encoding="utf-8")


def score_finished(client: genai.Client, now: datetime) -> None:
    scored_rows: list[dict[str, Any]] = []
    for path in list_prediction_files():
        versions = load_json(path, [])
        if not versions:
            continue
        latest_meta = versions[-1]
        try:
            kickoff = parse_iso(str(latest_meta["kickoff_utc"]))
        except (KeyError, ValueError):
            continue
        if kickoff > now:
            continue

        mid = path.stem
        result_path = RESULTS_DIR / f"{mid}.json"
        existing = load_json(result_path, None)
        if existing is not None and not isinstance(existing, dict):
            existing = None

        looked_up = None
        if existing is None or not existing.get("locked"):
            try:
                looked_up = lookup_result(client, latest_meta, now)
            except Exception as exc:  # noqa: BLE001 - keep scoring other matches
                print(f"Result lookup failed for {mid}: {exc}")
                if existing is None:
                    continue

        result = merge_result(existing, looked_up, kickoff, now)
        if result is None:
            print(f"No verified result yet for {mid}")
            continue
        if result != existing:
            write_json(result_path, result)

        prediction = prediction_before_kickoff(versions, kickoff)
        if prediction is None:
            print(f"No pre-kickoff prediction for {mid}; skipping score.")
            continue
        # Only publish unlocked results to the scoreboard after at least one lookup,
        # but still show them (provisional) so the board is useful during the day.
        scored = score_row(prediction, result)
        scored_rows.append(
            {
                "match_id": mid,
                "prediction": prediction,
                "result": result,
                "scored": scored,
            }
        )

    if scored_rows:
        scored_rows.sort(key=lambda row: row["prediction"].get("kickoff_utc", ""))
        rebuild_scoreboard(scored_rows)
    else:
        print("No scored matches yet; scoreboard unchanged.")


def predict_upcoming(client: genai.Client, now: datetime) -> None:
    try:
        fixtures = discover_fixtures(client, now)
    except Exception as exc:  # noqa: BLE001
        print(f"Fixture discovery failed: {exc}")
        return
    print(f"Found {len(fixtures)} fixture(s) in the next {LOOKAHEAD_HOURS}h.")
    for match in fixtures:
        mid = match_id(match["kickoff_utc"], match["home_team"], match["away_team"])
        try:
            fresh_now = utc_now()
            if not kickoff_still_upcoming(match["kickoff_utc"], fresh_now):
                print(f"Skipping {mid}: kickoff no longer upcoming.")
                continue
            print(f"Predicting {mid} ...")
            version = predict_one(client, match, fresh_now)
            append_prediction(match, version)
        except Exception as exc:  # noqa: BLE001 - isolate per-match failures
            print(f"Failed predicting {mid}: {exc}")


def main() -> None:
    require_api_key()
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    now = utc_now()
    print(f"RLWC predictor starting at {iso_z(now)} (model={MODEL}, dry_run={DRY_RUN})")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    predict_upcoming(client, now)
    score_finished(client, now)
    print("Done.")


if __name__ == "__main__":
    main()