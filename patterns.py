import time
import logging
from datetime import datetime, timezone

from config import DB_PATTERNS
from models import GroupPattern
import config

log = logging.getLogger("patterns")

RECALC_INTERVAL = 86400


def recalculate_patterns():
    import sqlite3
    conn = sqlite3.connect(str(DB_PATTERNS))
    conn.row_factory = sqlite3.Row

    tier1_groups = [g.lower() for g in config.get_groups().get("tier1", [])]

    groups = conn.execute(
        "SELECT DISTINCT group_name FROM upload_log WHERE pub_timestamp > ?",
        (time.time() - 7 * 86400,)
    ).fetchall()

    for row in groups:
        gname = row["group_name"]
        if not gname:
            continue

        if gname.lower() not in tier1_groups:
            continue

        hours = conn.execute("""
            SELECT hour, COUNT(*) as cnt
            FROM upload_log WHERE group_name=? AND pub_timestamp > ?
            GROUP BY hour ORDER BY cnt DESC
        """, (gname, time.time() - 7 * 86400)).fetchall()

        if not hours:
            continue

        total = sum(h["cnt"] for h in hours)
        avg_per_day = round(total / 7, 1)

        peak_hour = hours[0]["hour"]
        peak_start = max(0, peak_hour - 2)
        peak_end = min(23, peak_hour + 2)

        days = conn.execute("""
            SELECT weekday, COUNT(*) as cnt
            FROM upload_log WHERE group_name=? AND pub_timestamp > ?
            GROUP BY weekday ORDER BY cnt DESC
        """, (gname, time.time() - 7 * 86400)).fetchall()

        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        peak_days = ",".join(day_names[d["weekday"]] for d in days[:3])

        last = conn.execute(
            "SELECT MAX(pub_timestamp) as lt FROM upload_log WHERE group_name=?",
            (gname,)
        ).fetchone()
        last_ts = last["lt"] if last else 0

        conn.execute("""
            INSERT OR REPLACE INTO group_patterns
            (group_name, peak_hour_start, peak_hour_end, peak_days,
             avg_per_day, total_seen, last_upload, calculated_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (gname, peak_start, peak_end, peak_days,
              avg_per_day, total, last_ts, time.time()))

    conn.commit()
    conn.close()
    log.info(f"Recalculated patterns for tier1 groups")


def get_active_groups_now() -> list[str]:
    import sqlite3
    now_hour = datetime.now(timezone.utc).hour
    tier1_groups = [g.lower() for g in config.get_groups().get("tier1", [])]
    conn = sqlite3.connect(str(DB_PATTERNS))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT group_name FROM group_patterns WHERE peak_hour_start <= ? AND peak_hour_end >= ?",
        (now_hour, now_hour)
    ).fetchall()
    conn.close()
    return [r["group_name"] for r in rows if r["group_name"].lower() in tier1_groups]


def get_pattern(group_name: str) -> GroupPattern | None:
    import sqlite3
    conn = sqlite3.connect(str(DB_PATTERNS))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM group_patterns WHERE group_name=?", (group_name,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return GroupPattern(
        group_name=row["group_name"],
        peak_hour_start=row["peak_hour_start"],
        peak_hour_end=row["peak_hour_end"],
        peak_days=row["peak_days"].split(",") if row["peak_days"] else [],
        avg_per_day=row["avg_per_day"],
        total_seen=row["total_seen"],
        last_upload=row["last_upload"],
    )


def get_daily_forecast() -> str:
    active = get_active_groups_now()
    if not active:
        return ""

    import sqlite3
    conn = sqlite3.connect(str(DB_PATTERNS))
    conn.row_factory = sqlite3.Row

    lines = ["📊 <b>Tier1 groups likely active now:</b>"]
    for gname in active[:10]:
        row = conn.execute(
            "SELECT * FROM group_patterns WHERE group_name=?", (gname,)
        ).fetchone()
        if row:
            last_ago = ""
            if row["last_upload"]:
                ago_h = (time.time() - row["last_upload"]) / 3600
                last_ago = f"Last: {ago_h:.0f}h ago"
            lines.append(
                f"  <code>{gname}</code> "
                f"{row['peak_hour_start']:02d}:00-{row['peak_hour_end']:02d}:00 UTC "
                f"({row['avg_per_day']}/day | {last_ago})"
            )

    conn.close()
    return "\n".join(lines)


def should_recalculate() -> bool:
    import sqlite3
    conn = sqlite3.connect(str(DB_PATTERNS))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT MAX(calculated_at) as last FROM group_patterns"
    ).fetchone()
    conn.close()
    if not row or not row["last"]:
        return True
    return (time.time() - row["last"]) > RECALC_INTERVAL