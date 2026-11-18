#!/usr/bin/env python3
"""Fetch 2026 NFL scores from ESPN's unofficial public scoreboard endpoint.

No packages required. Writes data/results.json and data/results.js for the site.
Fails closed: if all requests fail, existing data is left unchanged.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = ROOT / "data" / "results.json"
TARGET_JS = ROOT / "data" / "results.js"
SEASON = 2026
ALIAS = {"JAC": "JAX", "WSH": "WAS", "LA": "LAR", "STL": "LAR", "SD": "LAC", "OAK": "LV"}
TEAMS = set("ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LV LAC LAR MIA MIN NE NO NYG NYJ PHI PIT SF SEA TB TEN WAS".split())


def normalize_team(code):
    return ALIAS.get(str(code or ""), str(code or ""))


def parse_event(event, stage, week):
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    c = competitions[0]
    sides = {p.get("homeAway"): p for p in c.get("competitors", [])}
    home, away = sides.get("home"), sides.get("away")
    if not home or not away:
        return None
    h, a = normalize_team(home.get("team", {}).get("abbreviation")), normalize_team(away.get("team", {}).get("abbreviation"))
    if h not in TEAMS or a not in TEAMS:
        return None
    when = event.get("date") or c.get("date")
    if not when:
        return None
    complete = event.get("status", {}).get("type", {}).get("completed") is True or c.get("status", {}).get("type", {}).get("completed") is True
    try:
        hs, ass = int(home.get("score")), int(away.get("score"))
    except (ValueError, TypeError):
        hs = ass = None
    win = None
    if complete:
        if home.get("winner") is True:
            win = h
        elif away.get("winner") is True:
            win = a
        elif hs is not None and ass is not None and hs != ass:
            win = h if hs > ass else a
    return {"id": str(event.get("id")), "date": when, "stage": stage, "week": week,
            "home": h, "away": a, "winner": win, "complete": bool(complete),
            "homeScore": hs, "awayScore": ass}


def fetch(week, stage, season_type):
    url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={SEASON}&seasontype={season_type}&week={week}"
    req = urllib.request.Request(url, headers={"User-Agent": "RepQuest-Friends-NFL-Tracker/1.0"})
    with urllib.request.urlopen(req, timeout=16) as response:
        return [parsed for event in json.load(response).get("events", []) if (parsed := parse_event(event, stage, week))]


def main():
    old = {str(x["id"]): x for x in json.loads(TARGET.read_text(encoding="utf-8")).get("games", [])} if TARGET.exists() else {}
    tasks = [(w, "regular", 2) for w in range(1, 19)] + [(1, "wildcard", 3), (2, "divisional", 3), (3, "conference", 3), (5, "superbowl", 3)]
    errors = []
    success = 0
    for week, stage, kind in tasks:
        try:
            games = fetch(week, stage, kind)
            for game in games:
                existing = old.get(game["id"])
                if existing and existing.get("complete") and not game.get("complete"):
                    continue
                old[game["id"]] = game
            success += 1
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, KeyError) as exc:
            errors.append(f"{stage} {week}: {exc}")
        time.sleep(0.08)
    if not success:
        raise SystemExit("Every ESPN request failed; existing data kept intact. " + "; ".join(errors[:2]))
    result = {"updatedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
              "games": sorted(old.values(), key=lambda g: (g["date"], g["id"]))}
    TARGET.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    TARGET_JS.write_text("window.NFL_RESULTS = " + json.dumps(result, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"Updated {success}/{len(tasks)} scoreboards; {len(result['games'])} games; {len(errors)} request errors")
    for error in errors:
        print("WARNING:", error)


if __name__ == "__main__":
    main()
