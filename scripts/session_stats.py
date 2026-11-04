"""今日の成績 (user's request): your results since Puyo Puyo Tetris 2 was
started, until it's closed — wins and losses, the current win streak, the
rating's change and your average APM / PPS / APP.

Worked out by the server (data_server) from what's already kept: the finished
matches (config/opener_history.json, written by the HUD) and the online
rating (config/rating_history.json). "Since the game started" is the game
process's own start time, so restarting this app keeps the day's results, and
closing the game starts afresh. Which side was you is noted with each match
("you", from the "You" card on the まちうけ screen just before it; 1P when
there was none, as offline).
"""

SIDES = ("left", "right")


def you_of(match):
    you = match.get("you")
    return you if you in SIDES else "left"


def summarize(matches, ratings, since):
    """The session's numbers (matches and ratings with t >= since), or None
    when nothing has happened in it yet."""
    if since is None:
        return None
    played = [m for m in matches if isinstance(m.get("t"), (int, float)) and m["t"] >= since
              and m.get("winner") in SIDES]
    played.sort(key=lambda m: m["t"])
    wins = sum(1 for m in played if m["winner"] == you_of(m))
    losses = len(played) - wins
    streak = 0
    for m in reversed(played):
        if m["winner"] != you_of(m):
            break
        streak += 1
    sums, counts = {}, {}
    for m in played:
        stats = (m.get(you_of(m)) or {}).get("stats") or {}
        for key in ("apm", "pps", "app"):
            v = stats.get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                sums[key] = sums.get(key, 0.0) + v
                counts[key] = counts.get(key, 0) + 1
    averages = {k: sums[k] / counts[k] for k in sums}
    rating = rating_change(ratings, since)
    if not played and rating is None:
        return None
    return {"wins": wins, "losses": losses, "matches": len(played), "streak": streak,
            "win_rate": round(100 * wins / len(played)) if played else None,
            "apm": averages.get("apm"), "pps": averages.get("pps"), "app": averages.get("app"),
            "rating": rating}


def rating_change(ratings, since):
    """The rating's change in the session, for the league read last in it:
    {"league", "before", "now", "delta"}, or None. Before = that league's last
    rating from before the session, or its first one in it."""
    points = [p for p in ratings if isinstance(p.get("t"), (int, float)) and isinstance(p.get("rating"), int)]
    points.sort(key=lambda p: p["t"])
    inside = [p for p in points if p["t"] >= since]
    if not inside:
        return None
    league = inside[-1].get("league")
    now = inside[-1]["rating"]
    earlier = [p["rating"] for p in points if p["t"] < since and p.get("league") == league]
    before = earlier[-1] if earlier else next(p["rating"] for p in inside if p.get("league") == league)
    return {"league": league, "before": before, "now": now, "delta": now - before}


def lines(summary, language="ja"):
    """The text shown (HUD and OBS alike): [(text, kind)], kind "title",
    "main" or "sub"."""
    if not summary:
        return []
    en = language == "en"
    out = [("Today" if en else "今日の成績", "title")]
    if summary["matches"]:
        w, l, rate = summary["wins"], summary["losses"], summary["win_rate"]
        out.append((f"{w}W {l}L  {rate}%" if en else f"{w}勝 {l}敗  {rate}%", "main"))
        if summary["streak"] >= 2:
            out.append((f"{summary['streak']} wins in a row" if en else f"{summary['streak']}連勝中", "sub"))
    r = summary.get("rating")
    if r:
        sign = "+" if r["delta"] > 0 else ("±" if r["delta"] == 0 else "")
        out.append((f"Rating {sign}{r['delta']} ({r['now']})" if en else f"レート {sign}{r['delta']}（{r['now']}）",
                    "sub"))
    avg = []
    for key, fmt in (("apm", "{:.1f}"), ("pps", "{:.2f}"), ("app", "{:.2f}")):
        if summary.get(key) is not None:
            avg.append(f"{key.upper()} {fmt.format(summary[key])}")
    if avg:
        out.append(("  ".join(avg), "sub"))
    return out
