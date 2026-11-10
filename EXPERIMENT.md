# Experiment status: FAILED

**Verdict:** This experiment is a failure. The tournament forecast run did not complete under the rules that make the results meaningful.

Pool-stage numbers in `SCOREBOARD.md` are a partial record only. They are **not** a valid full-tournament outcome.

## What the experiment was

An unattended Gemini agent was meant to:

1. Forecast each men’s and women’s RLWC 2026 match **before kickoff**
2. Commit that forecast as an audit trail
3. Look up final scores and measure hit rate, Brier score, and margin error through the finals

No money was involved. Honesty of timing mattered more than the raw accuracy numbers.

## The gap

From **2026-11-06 08:36 UTC** through at least **2026-11-10**, every Gemini API call in the scheduled workflow failed.

| Match | Kickoff (UTC) | Prediction | Result / score |
|---|---|---|---|
| Women — New Zealand vs Samoa | 2026-11-07 06:45 | Made 2026-11-06 00:42 UTC | Never recorded (stuck Pending) |
| Men — New Zealand vs Tonga | 2026-11-07 09:05 | Made 2026-11-06 00:42 UTC | Never recorded (stuck Pending) |
| Women — Australia vs Fiji | 2026-11-08 06:45 | **Never made** | n/a |
| Men — Australia vs Samoa | 2026-11-08 09:05 | **Never made** | n/a |

Knockout coverage therefore stopped before the semi-finals were complete. That breaks the experiment’s claim of an end-to-end tournament measure.

## Root cause (plain language)

The workflow installed `google-genai>=1.0.0` on every run (no pin).

- **2026-11-06 00:42 UTC** — still on `google-genai 2.34.0`; Nov 7 semis were predicted successfully
- **2026-11-06 02:29 UTC** — `google-genai 3.0.0` published on PyPI
- **2026-11-06 08:36 UTC onward** — Actions pulled `3.0.0`, which talks to Gemini API `v1` by default; the bot’s `system_instruction` is rejected there with `400 INVALID_ARGUMENT`

Discovery, prediction, and result lookup all use that same call path, so all three stopped.

## Why it looked healthy

Errors were caught and logged. The job still exited green. Later “Predictions and scores” commits often only bumped the scoreboard timestamp. There was no alert when forecasts or scores stopped arriving.

## Integrity rule (no backfill)

Missed pre-kickoff forecasts must **not** be recreated after the fact with live web search. Post-match information would contaminate them. Nov 8 semis stay unmarked. Nov 7 may keep their existing pre-kickoff predictions, but without recorded results they remain incomplete.

## Lessons

1. Pin third-party majors used in production schedules (`google-genai==2.34.0` or `<3`).
2. Fail the workflow when Gemini discovery or result lookup fails.
3. Alert when a run inside the tournament window produces no prediction/result activity while fixtures are due.
4. Do not treat a green Actions check as proof the experiment advanced.

## References

- Workflow: `.github/workflows/predict.yml`
- Runner: `src/run.py` (`gemini_json`, `predict_upcoming`, `score_finished`)
- Last successful semi predictions commit on remote: `4223742` (2026-11-06 00:42 UTC)
- Failure onset in Actions: run starting 2026-11-06 08:36 UTC
