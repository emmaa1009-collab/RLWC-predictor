# Experiment status: FAILED

**Verdict:** This experiment is a failure. The tournament forecast run did not complete under the rules that make the results meaningful.

Pool-stage numbers on this scoreboard are a partial record only. They are **not** a valid full-tournament outcome.

Full write-up (same content): [`../EXPERIMENT.md`](../EXPERIMENT.md) in the repository root.

## The gap

From **2026-11-06 08:36 UTC** through at least **2026-11-10**, every Gemini API call in the scheduled workflow failed.

| Match | Kickoff (UTC) | Prediction | Result / score |
|---|---|---|---|
| Women — New Zealand vs Samoa | 2026-11-07 06:45 | Made 2026-11-06 00:42 UTC | Never recorded (stuck Pending) |
| Men — New Zealand vs Tonga | 2026-11-07 09:05 | Made 2026-11-06 00:42 UTC | Never recorded (stuck Pending) |
| Women — Australia vs Fiji | 2026-11-08 06:45 | **Never made** | n/a |
| Men — Australia vs Samoa | 2026-11-08 09:05 | **Never made** | n/a |

## Root cause

Unpinned `google-genai>=1.0.0` pulled **3.0.0** (published 2026-11-06 02:29 UTC). That release defaults to API `v1`, which rejects this project’s `system_instruction`. Discovery, prediction, and result lookup all stopped. Jobs stayed green because errors were swallowed.

## Integrity rule

Missed pre-kickoff forecasts must **not** be recreated after the fact with live web search.
