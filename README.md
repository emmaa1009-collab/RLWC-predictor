# RLWC Predictor

An experiment to see how accurately an AI agent can predict the results of the 2026 Rugby League World Cup — **men's and women's** tournaments (roughly 15 October to 15 November 2026, Australia, New Zealand and Papua New Guinea). The women's competition starts about a day after the men's.

No money is involved. The point is to measure, honestly, how well the agent does compared with simple baselines.

Everything runs on its own. You set it up once and then check the scoreboard whenever you like.

## How it works

A GitHub Actions workflow runs twice a day during the tournament window. Each run does three things:

1. **Predict.** Gemini searches the web (Google Search grounding) for men's and women's matches kicking off in the next 36 hours. For each one it researches recent form, squad and injury news, rankings, venue and head-to-head record, then outputs a win probability for each team and a predicted margin.
2. **Record.** The prediction is saved to `data/predictions/` and committed to this repo. The commit history is the audit trail showing each prediction was made before kickoff.
3. **Score.** For any match that has finished, the agent looks up the final score, saves it to `data/results/`, and updates `SCOREBOARD.md` (Overall, Men, and Women summaries).

The prompt is built into `src/run.py`, so nothing needs to be written by hand before each match.

## Repo layout

```
.github/workflows/predict.yml   Schedule and automation
src/run.py                      Predict, record and score logic (with the built-in prompt)
requirements.txt                Python dependencies
data/predictions/               One JSON file per match, append-only list of versions
data/results/                   One JSON file per finished match
SCOREBOARD.md                   Auto-generated running results
```

## Setup

1. **Create a new GitHub repo** and push these files to it. Public or private both work.
2. **Get a free Gemini API key** from [Google AI Studio](https://aistudio.google.com/apikey). No credit card needed for the free tier.
3. **Add the key as a secret.** In the repo go to Settings → Secrets and variables → Actions → New repository secret. Name it `GEMINI_API_KEY`.
4. **Allow the workflow to push.** In Settings → Actions → General → Workflow permissions, choose "Read and write permissions".
5. **Test it.** Go to the Actions tab, pick "RLWC predictions", choose Run workflow, and tick `dry_run`. This prints predictions in the log without committing anything.
6. **Let it run.** From 14 October the schedule takes over. Outside 14 October to 16 November the scheduled runs skip themselves.

Optional: set a repository variable named `GEMINI_MODEL` (Settings → Secrets and variables → Actions → Variables) to change the model. The default is `gemini-2.5-flash`.

## Schedule

Times below are for the schedule as written in the workflow (GitHub uses UTC).

| Run | UTC | Sydney (AEDT) | Purpose |
|---|---|---|---|
| Morning | 20:00 | 07:00 | Picks up overnight team news and scores finished games |
| Pre-kickoff | 02:00 | 13:00 | Final update before evening kickoffs |

GitHub scheduled runs can start a few minutes late, and occasionally much later at busy times. If you want tighter control, add a third run closer to kickoff by adding another `cron` line.

## What gets recorded

Each match has one file in `data/predictions/`, for example `2026-10-16_women_australia_new-zealand.json`. Filenames include the competition (`men` or `women`) so same-name fixtures do not collide. Each file holds a list of versions, and each version has:

- `competition`: `men` or `women`
- `made_at`: UTC timestamp of the prediction
- `home_win_prob` and `away_win_prob`: probabilities that sum to 1 (there are no draws in knockout games, and draws are rare enough in pool games to be folded in or tracked separately, see Limitations)
- `predicted_margin`: predicted winning margin in points
- `reasoning`: a short summary of the evidence the agent used

Files are append-only. A new version is added if a later run finds changed information (for example a late team change), and earlier versions are never edited or deleted.

**The scored prediction is the latest version made before kickoff.**

## Scoring

Three measures are tracked, each compared with baselines, for **Overall**, **Men**, and **Women**.

- **Hit rate.** The percentage of matches where the team given more than 50% won.
- **Brier score.** For each match, take the probability the agent gave to the actual winner, subtract it from 1, and square the result. Average across matches. Lower is better. Always guessing 50/50 scores 0.25, and a perfect forecaster scores 0.
- **Margin error.** The average absolute difference between the predicted and actual winning margin.

Baselines in the scoreboard:

- **Ranking baseline:** always pick the higher-ranked team (using ranks stored on each prediction, within that competition)
- **Coin flip:** 50/50 on every match (Brier 0.25)

If you want a market comparison, you can paste bookmaker-implied probabilities into `data/baseline_odds.json` by hand before kickoff. You are only reading the odds here, not betting.

## Rules that keep the experiment honest

- Predictions are made and committed before kickoff, never after.
- Earlier versions are never edited or removed.
- The agent is not shown results of the match it is predicting.
- Men's and women's evidence are kept separate.
- Do not hand edit files in `data/predictions/` once the tournament starts.

## Cost

Designed to run on the **Gemini free tier** (AI Studio API key, no billing required). GitHub Actions is free for this workload on a public repo, and within the free private-repo minute allowance.

Free-tier rate limits reset daily. Two runs a day across men's plus women's fixtures uses more quota than men-only; if a run fails with a quota error, re-run it later from the Actions tab.

## Limitations

- **Small sample.** Roughly 20 men's matches and a smaller women's draw. Interesting for comparison, not statistical proof. A single upset can move the Brier score a lot.
- **Draws.** Pool matches can end in a draw. By default these are scored as 0.5 for each side. If you would rather exclude draws, change `DRAW_HANDLING` in `src/run.py` (or set the `DRAW_HANDLING` env var to `exclude`).
- **Result lookups.** The agent finds scores through web search. Results stay provisional until two agreeing lookups (or 24 hours after kickoff), then lock. If a result is still wrong, edit the match file in `data/results/` by hand; the scoreboard rebuilds on the next run.
- **No live-score leakage.** Matches that have already kicked off are never predicted.
- **Information cutoff.** The agent can only use what it can find on the web at the time of each run, so thin or conflicting coverage of a team will show up as lower confidence or lower quality predictions.

## Troubleshooting

| Problem | What to check |
|---|---|
| Workflow fails at push | Workflow permissions set to "Read and write" (setup step 4) |
| `GEMINI_API_KEY` error | Secret name spelled exactly, and set under Actions secrets |
| Quota / 429 errors | Free-tier daily limit hit; wait and re-run, or switch `GEMINI_MODEL` |
| No predictions appear | Check the run is inside 14 October to 16 November, or trigger it manually |
| Duplicate or missing matches | Open the run log and check the fixture list the agent found |
| Run skipped | The window check step prints the reason in the log |

## Ending the experiment

After the finals around 15 November, the scheduled runs skip themselves from 17 November. `SCOREBOARD.md` will hold the final tally.
