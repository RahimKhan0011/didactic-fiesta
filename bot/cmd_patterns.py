import time
import sqlite3
import config


def _patterns(args: str) -> str:
    tier1_groups = [g.lower() for g in config.get_groups().get("tier1", [])]

    conn = sqlite3.connect(str(config.DB_MAIN))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT parsed_group, COUNT(*) as cnt
        FROM torrents
        WHERE parsed_group IS NOT NULL AND parsed_group != '' AND first_seen > ?
        GROUP BY parsed_group ORDER BY cnt DESC
    """, (time.time() - 7 * 86400,)).fetchall()
    conn.close()

    tier1_rows = [r for r in rows if r["parsed_group"] and r["parsed_group"].lower() in tier1_groups]

    if not tier1_rows:
        return "No tier1 pattern data yet\nNeed ~1 week of data"

    lines = ["📊 <b>Tier1 Group Patterns (7 days)</b>"]
    for r in tier1_rows[:15]:
        from patterns import get_pattern
        p = get_pattern(r["parsed_group"])
        if p:
            lines.append(
                f"<code>{p.group_name}</code> — {p.total_seen} releases\n"
                f"  Peak: {p.peak_hour_start:02d}:00-{p.peak_hour_end:02d}:00 UTC\n"
                f"  Avg: {p.avg_per_day}/day | Days: {', '.join(p.peak_days)}"
            )
        else:
            lines.append(f"<code>{r['parsed_group']}</code> — {r['cnt']} releases")

    from patterns import get_daily_forecast
    forecast = get_daily_forecast()
    if forecast:
        lines.append(f"\n{forecast}")

    return "\n".join(lines)


def _forecast(args: str) -> str:
    from patterns import get_daily_forecast
    forecast = get_daily_forecast()
    return forecast if forecast else "No tier1 pattern data yet\nNeed ~1 week of data"


HANDLERS = {
    "/patterns": _patterns,
    "/forecast": _forecast,
}