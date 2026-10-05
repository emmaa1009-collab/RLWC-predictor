"""Static HTML scoreboard for docs/ (local open or optional GitHub Pages)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"

# Filled by write_docs_site; kept as one self-contained page for file:// and Pages.
SCOREBOARD_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RLWC Predictor</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet" />
  <style>
    :root {
      --pitch-deep: #071a14;
      --pitch: #0d3326;
      --grass: #1a5c43;
      --mist: #e7efe9;
      --line: rgba(231, 239, 233, 0.14);
      --whistle: #e0b13a;
      --good: #3dba7a;
      --bad: #e25b5b;
      --muted: rgba(231, 239, 233, 0.68);
      --ink: #f4f8f5;
    }

    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      font-family: "IBM Plex Sans", system-ui, sans-serif;
      background:
        radial-gradient(ellipse 90% 55% at 50% -10%, rgba(224, 177, 58, 0.16), transparent 55%),
        linear-gradient(165deg, var(--pitch-deep) 0%, var(--pitch) 45%, #0a281e 100%);
      background-attachment: fixed;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: 0.07;
      background-image: repeating-linear-gradient(
        -12deg,
        transparent,
        transparent 11px,
        rgba(231, 239, 233, 0.7) 11px,
        rgba(231, 239, 233, 0.7) 12px
      );
    }

    .wrap {
      position: relative;
      width: min(1080px, calc(100% - 2rem));
      margin: 0 auto;
      padding: 2.5rem 0 4rem;
    }

    .hero {
      padding: 2.5rem 0 2rem;
      border-bottom: 1px solid var(--line);
      animation: rise 0.7s ease-out both;
    }
    .brand {
      margin: 0;
      font-family: "Barlow Condensed", sans-serif;
      font-weight: 800;
      font-size: clamp(3rem, 10vw, 5.5rem);
      line-height: 0.92;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }
    .brand span { color: var(--whistle); }
    .lede {
      margin: 1rem 0 0;
      max-width: 34rem;
      color: var(--muted);
      font-size: 1.05rem;
      line-height: 1.5;
    }
    .meta {
      margin-top: 1.25rem;
      color: var(--muted);
      font-size: 0.9rem;
    }

    section {
      margin-top: 2.75rem;
      animation: rise 0.75s ease-out both;
    }
    section:nth-of-type(2) { animation-delay: 0.08s; }
    section:nth-of-type(3) { animation-delay: 0.14s; }

    h2 {
      margin: 0 0 1rem;
      font-family: "Barlow Condensed", sans-serif;
      font-size: 1.75rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    .summary-grid {
      display: grid;
      gap: 1.25rem;
    }
    @media (min-width: 800px) {
      .summary-grid { grid-template-columns: repeat(3, 1fr); }
    }
    .summary-block h3 {
      margin: 0 0 0.75rem;
      font-family: "Barlow Condensed", sans-serif;
      font-size: 1.2rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--whistle);
    }
    .metrics {
      display: grid;
      gap: 0.65rem;
    }
    .metric {
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      padding: 0.55rem 0;
      border-bottom: 1px solid var(--line);
      font-size: 0.95rem;
    }
    .metric span:last-child { font-weight: 600; }

    .filters {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-bottom: 1.25rem;
    }
    .filters button {
      appearance: none;
      border: 1px solid var(--line);
      background: transparent;
      color: var(--mist);
      font: inherit;
      font-size: 0.9rem;
      padding: 0.45rem 0.9rem;
      cursor: pointer;
      transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
    }
    .filters button:hover,
    .filters button:focus-visible {
      border-color: var(--whistle);
      color: var(--whistle);
      outline: none;
    }
    .filters button[aria-pressed="true"] {
      background: rgba(224, 177, 58, 0.16);
      border-color: var(--whistle);
      color: var(--whistle);
    }
    .filters button:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }

    .match-list { display: grid; gap: 0; }
    .match {
      display: grid;
      gap: 0.75rem;
      padding: 1.25rem 0;
      border-bottom: 1px solid var(--line);
      animation: rise 0.55s ease-out both;
    }
    @media (min-width: 720px) {
      .match {
        grid-template-columns: 6.5rem 1fr auto;
        align-items: start;
        gap: 1.25rem;
      }
    }
    .comp {
      font-family: "Barlow Condensed", sans-serif;
      font-size: 0.95rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--whistle);
    }
    .fixture {
      margin: 0;
      font-family: "Barlow Condensed", sans-serif;
      font-size: 1.45rem;
      font-weight: 700;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }
    .detail {
      margin: 0.35rem 0 0;
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.45;
    }
    .outcome {
      text-align: left;
    }
    @media (min-width: 720px) {
      .outcome { text-align: right; min-width: 9rem; }
    }
    .score {
      margin: 0;
      font-family: "Barlow Condensed", sans-serif;
      font-size: 2rem;
      font-weight: 800;
      letter-spacing: 0.04em;
    }
    .badge {
      display: inline-block;
      margin-top: 0.35rem;
      font-size: 0.8rem;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .badge.hit { color: var(--good); }
    .badge.miss { color: var(--bad); }
    .badge.half { color: var(--whistle); }
    .badge.pending { color: var(--muted); }
    .badge.scheduled { color: var(--muted); }
    .empty {
      padding: 1.5rem 0;
      color: var(--muted);
      border-bottom: 1px solid var(--line);
    }

    footer {
      margin-top: 3rem;
      padding-top: 1.25rem;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.85rem;
      line-height: 1.5;
    }

    @keyframes rise {
      from { opacity: 0; transform: translateY(12px); }
      to { opacity: 1; transform: translateY(0); }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <header class="hero">
      <h1 class="brand">RLWC <span>Predictor</span></h1>
      <p class="lede">Men’s and women’s Rugby League World Cup 2026 — forecasts locked before kickoff, scored against the real results.</p>
      <p class="meta" id="updated">Loading…</p>
    </header>

    <section aria-labelledby="summary-heading">
      <h2 id="summary-heading">Summary</h2>
      <div class="summary-grid" id="summaries"></div>
    </section>

    <section aria-labelledby="matches-heading">
      <h2 id="matches-heading">Matches</h2>
      <div class="filters" role="group" aria-label="Filter by competition">
        <button type="button" data-filter="all" aria-pressed="true">All</button>
        <button type="button" data-filter="men" aria-pressed="false">Men</button>
        <button type="button" data-filter="women" aria-pressed="false">Women</button>
      </div>
      <div class="match-list" id="matches"></div>
    </section>

    <footer>
      Predictions are append-only and scored only if made before kickoff.
      Results stay provisional until confirmed. Opening this file from a private
      repo keeps it private; enabling GitHub Pages usually publishes it publicly.
    </footer>
  </main>

  <script id="scoreboard-data" type="application/json">__SCOREBOARD_JSON__</script>
  <script>
    const data = JSON.parse(document.getElementById("scoreboard-data").textContent);

    function pct(value) {
      if (value === null || value === undefined) return "n/a";
      return (value * 100).toFixed(1) + "%";
    }
    function num(value, digits = 3) {
      if (value === null || value === undefined) return "n/a";
      return Number(value).toFixed(digits);
    }
    function hitLabel(hit) {
      if (hit === null || hit === undefined) return { text: "Pending", cls: "pending" };
      if (hit === 1) return { text: "Hit", cls: "hit" };
      if (hit === 0.5) return { text: "Half", cls: "half" };
      return { text: "Miss", cls: "miss" };
    }
    function esc(text) {
      return String(text)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function renderSummary(title, stats) {
      return `
        <div class="summary-block">
          <h3>${esc(title)}</h3>
          <div class="metrics">
            <div class="metric"><span>Hit rate</span><span>${pct(stats.hit_rate)}</span></div>
            <div class="metric"><span>Brier</span><span>${num(stats.brier)}</span></div>
            <div class="metric"><span>Margin err</span><span>${num(stats.margin_error, 2)}</span></div>
            <div class="metric"><span>Rank baseline</span><span>${pct(stats.ranking_hit_rate)}</span></div>
            <div class="metric"><span>Matches</span><span>${stats.count ?? 0}</span></div>
          </div>
        </div>`;
    }

    function renderMatch(match) {
      const pred = match.prediction || {};
      const result = match.result;
      const scored = match.scored;
      const home = pred.home_team || match.home_team || "";
      const away = pred.away_team || match.away_team || "";
      const kickoff = pred.kickoff_utc || match.kickoff_utc || "";
      const venue = match.venue || pred.venue || "";
      const venueBit = venue ? ` · ${esc(venue)}` : "";
      let middle = "";
      let scoreHtml = `<p class="score">TBD</p>`;
      let badge = hitLabel(null);

      if (match.status === "scheduled" || !match.prediction) {
        middle = `<p class="detail">Kickoff ${esc(kickoff)}${venueBit}</p>`;
        badge = { text: "No prediction yet", cls: "scheduled" };
      } else {
        const homeP = Math.round((pred.home_win_prob || 0) * 100);
        const awayP = Math.round((pred.away_win_prob || 0) * 100);
        const pick = pred.predicted_winner === "away" ? pred.away_team : pred.home_team;
        const reason = pred.reasoning ? `<p class="detail">${esc(pred.reasoning)}</p>` : "";
        middle = `<p class="detail">Pick ${esc(pick)} (${homeP}–${awayP}) · margin ${esc(pred.predicted_margin ?? "n/a")} · kickoff ${esc(kickoff)}${venueBit}</p>${reason}`;
        if (result) {
          scoreHtml = `<p class="score">${result.home_score}–${result.away_score}</p>`;
          badge = hitLabel(scored ? scored.hit : null);
          if (scored) {
            badge.text += ` · Brier ${num(scored.brier)}`;
          }
          if (!result.locked) badge.text += " · provisional";
        } else {
          badge = { text: "Pending", cls: "pending" };
        }
      }
      return `
        <article class="match" data-competition="${esc(match.competition)}">
          <div class="comp">${esc(match.competition === "women" ? "Women" : "Men")}</div>
          <div>
            <p class="fixture">${esc(home)} vs ${esc(away)}</p>
            ${middle}
          </div>
          <div class="outcome">
            ${scoreHtml}
            <span class="badge ${badge.cls}">${esc(badge.text)}</span>
          </div>
        </article>`;
    }

    document.getElementById("updated").textContent = data.updated
      ? `Updated ${data.updated}`
      : "No update yet";

    const summaries = data.summaries || {};
    document.getElementById("summaries").innerHTML = [
      renderSummary("Overall", summaries.overall || { count: 0 }),
      renderSummary("Men", summaries.men || { count: 0 }),
      renderSummary("Women", summaries.women || { count: 0 }),
    ].join("");

    const matchesEl = document.getElementById("matches");
    const matches = data.matches || [];
    if (!matches.length) {
      matchesEl.innerHTML = `<p class="empty">No pool fixtures loaded yet. Add matches to data/fixtures.json or wait for the workflow to record forecasts.</p>`;
    } else {
      matchesEl.innerHTML = matches.map(renderMatch).join("");
    }

    const buttons = document.querySelectorAll(".filters button");
    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        const filter = button.getAttribute("data-filter");
        buttons.forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
        document.querySelectorAll(".match").forEach((node) => {
          const show = filter === "all" || node.getAttribute("data-competition") === filter;
          node.hidden = !show;
        });
      });
    });
  </script>
</body>
</html>
"""


def empty_stats() -> dict[str, Any]:
    return {
        "count": 0,
        "hit_rate": None,
        "ranking_hit_rate": None,
        "brier": None,
        "market_hit_rate": None,
        "market_brier": None,
        "margin_error": None,
    }


def serialize_stats(stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "count": int(stats.get("count") or 0),
        "hit_rate": stats.get("hit_rate"),
        "ranking_hit_rate": stats.get("ranking_hit_rate"),
        "brier": stats.get("brier"),
        "market_hit_rate": stats.get("market_hit_rate"),
        "market_brier": stats.get("market_brier"),
        "margin_error": stats.get("margin_error"),
    }


def build_site_payload(
    *,
    updated: str,
    scored_rows: list[dict[str, Any]],
    pending_rows: list[dict[str, Any]],
    overall: dict[str, Any],
    men: dict[str, Any],
    women: dict[str, Any],
    scheduled_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    present_ids: set[str] = set()

    for row in scored_rows:
        pred = row["prediction"]
        result = row["result"]
        scored = row["scored"]
        present_ids.add(row["match_id"])
        matches.append(
            {
                "match_id": row["match_id"],
                "competition": pred.get("competition") or "men",
                "kickoff_utc": pred.get("kickoff_utc"),
                "home_team": pred.get("home_team"),
                "away_team": pred.get("away_team"),
                "venue": pred.get("venue") or "",
                "stage": pred.get("stage") or "pool",
                "status": "scored",
                "prediction": {
                    "home_team": pred.get("home_team"),
                    "away_team": pred.get("away_team"),
                    "kickoff_utc": pred.get("kickoff_utc"),
                    "venue": pred.get("venue") or "",
                    "made_at": pred.get("made_at"),
                    "home_win_prob": pred.get("home_win_prob"),
                    "away_win_prob": pred.get("away_win_prob"),
                    "predicted_margin": pred.get("predicted_margin"),
                    "predicted_winner": pred.get("predicted_winner"),
                    "reasoning": pred.get("reasoning"),
                },
                "result": {
                    "home_score": result.get("home_score"),
                    "away_score": result.get("away_score"),
                    "locked": bool(result.get("locked")),
                    "source": result.get("source"),
                },
                "scored": {
                    "hit": scored.get("hit"),
                    "brier": scored.get("brier"),
                    "margin_error": scored.get("margin_error"),
                    "ranking_hit": scored.get("ranking_hit"),
                    "pred_side": scored.get("pred_side"),
                },
            }
        )

    for row in pending_rows:
        if row["match_id"] in present_ids:
            continue
        pred = row["prediction"]
        present_ids.add(row["match_id"])
        matches.append(
            {
                "match_id": row["match_id"],
                "competition": pred.get("competition") or "men",
                "kickoff_utc": pred.get("kickoff_utc"),
                "home_team": pred.get("home_team"),
                "away_team": pred.get("away_team"),
                "venue": pred.get("venue") or "",
                "stage": pred.get("stage") or "pool",
                "status": "pending",
                "prediction": {
                    "home_team": pred.get("home_team"),
                    "away_team": pred.get("away_team"),
                    "kickoff_utc": pred.get("kickoff_utc"),
                    "venue": pred.get("venue") or "",
                    "made_at": pred.get("made_at"),
                    "home_win_prob": pred.get("home_win_prob"),
                    "away_win_prob": pred.get("away_win_prob"),
                    "predicted_margin": pred.get("predicted_margin"),
                    "predicted_winner": pred.get("predicted_winner"),
                    "reasoning": pred.get("reasoning"),
                },
                "result": None,
                "scored": None,
            }
        )

    for row in scheduled_rows or []:
        mid = row["match_id"]
        if mid in present_ids:
            continue
        matches.append(
            {
                "match_id": mid,
                "competition": row.get("competition") or "men",
                "kickoff_utc": row.get("kickoff_utc"),
                "home_team": row.get("home_team"),
                "away_team": row.get("away_team"),
                "venue": row.get("venue") or "",
                "stage": row.get("stage") or "pool",
                "pool": row.get("pool") or "",
                "status": "scheduled",
                "prediction": None,
                "result": None,
                "scored": None,
            }
        )

    matches.sort(key=lambda item: (item.get("kickoff_utc") or "", item.get("competition") or ""))

    return {
        "updated": updated,
        "summaries": {
            "overall": serialize_stats(overall),
            "men": serialize_stats(men),
            "women": serialize_stats(women),
        },
        "matches": matches,
    }


def render_index_html(payload: dict[str, Any]) -> str:
    embedded = json.dumps(payload, indent=2)
    # Prevent accidental </script> breaks inside JSON strings.
    embedded = embedded.replace("<", "\\u003c")
    return SCOREBOARD_PAGE.replace("__SCOREBOARD_JSON__", embedded)


def write_docs_site(payload: dict[str, Any], *, dry_run: bool = False) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = DOCS_DIR / "scoreboard.json"
    html_path = DOCS_DIR / "index.html"
    html = render_index_html(payload)
    if dry_run:
        print(f"[dry_run] would write {json_path.relative_to(DOCS_DIR.parent)}")
        print(f"[dry_run] would write {html_path.relative_to(DOCS_DIR.parent)}")
        return
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
