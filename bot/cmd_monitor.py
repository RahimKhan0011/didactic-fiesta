import time
from datetime import datetime, timezone

import config
import db
import quiet as quiet_mod
import tracker
from bot.polling import get_start_time


def _status(args: str) -> str:
    q = "🔇 QUIET" if quiet_mod.is_quiet() else "🔊 ACTIVE"
    queued = quiet_mod.get_queue_size()
    stats = db.get_stats()
    uptime = _format_uptime()
    alerts = config.get_tier_alerts()
    t1 = "🟢" if alerts.get("tier1", True) else "🔴"
    t2 = "🟢" if alerts.get("tier2", True) else "🔴"
    t3 = "🟢" if alerts.get("tier3", True) else "🔴"
    return (
        f"📡 <b>TorrentLeech Monitor Status</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"State: {q}\n"
        f"Uptime: {uptime}\n"
        f"DB: {stats['total']} torrents ({stats['today']} today)\n"
        f"Notified: {stats['notified']}\n"
        f"Tracking: {stats['tracked_shows']} shows\n"
        f"Queued: {queued}\n\n"
        f"Tier alerts: {t1} T1 | {t2} T2 | {t3} T3"
    )


def _stats(args: str) -> str:
    stats = db.get_stats()
    return (
        f"📊 <b>Database Stats</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total torrents: {stats['total']}\n"
        f"Today: {stats['today']}\n"
        f"Notified: {stats['notified']}\n"
        f"Tracked shows: {stats['tracked_shows']}"
    )


def _ping(args: str) -> str:
    return "🏓 Pong"


def _uptime(args: str) -> str:
    return f"⏱ Uptime: {_format_uptime()}"


def _interval(args: str) -> str:
    si = config.get_smart_interval()
    now_h = datetime.now(timezone.utc).hour
    peak = si.get("peak_hours", [16, 23])
    dead = si.get("dead_hours", [2, 7])

    base = config.BASE_INTERVAL
    if peak[0] <= now_h < peak[1]:
        current = int(base * si.get("peak_multiplier", 0.5))
        mode = "🟢 PEAK"
    elif dead[0] <= now_h < dead[1]:
        current = int(base * si.get("dead_multiplier", 2.0))
        mode = "🔴 DEAD"
    else:
        current = base
        mode = "🟡 NORMAL"

    return (
        f"⏱ <b>Interval</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Base: {base}s\n"
        f"Current mode: {mode}\n"
        f"Current interval: ~{current}s\n"
        f"UTC hour: {now_h}\n"
        f"Peak: {peak[0]:02d}:00-{peak[1]:02d}:00\n"
        f"Dead: {dead[0]:02d}:00-{dead[1]:02d}:00\n"
        f"Tier1 burst: {si.get('tier1_burst', 20)}s"
    )


def _feeds(args: str) -> str:
    feeds = config.get_feeds()
    if not feeds:
        return "No feeds configured"
    lines = ["📡 <b>TorrentLeech RSS Feeds</b>\n"]
    for f in feeds:
        name = f.get("name", "unnamed")
        url = f.get("url", "?")
        safe = url[:40] + "..." if len(url) > 40 else url
        lines.append(f"  • {name}\n    <code>{safe}</code>")
    return "\n".join(lines)


def _reload(args: str) -> str:
    config.reload_yaml()
    tracker.init_tracked_shows()
    feeds = len(config.get_feeds())
    profiles = len(config.get_profiles())
    shows = len(config.get_shows())
    return (
        f"✅ Config reloaded\n"
        f"Feeds: {feeds}\n"
        f"Profiles: {profiles}\n"
        f"Shows: {shows}"
    )


def _format_uptime() -> str:
    elapsed = time.time() - get_start_time()
    days = int(elapsed // 86400)
    hours = int((elapsed % 86400) // 3600)
    mins = int((elapsed % 3600) // 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{mins}m")
    return " ".join(parts)


HANDLERS = {
    "/status": _status,
    "/stats": _stats,
    "/ping": _ping,
    "/uptime": _uptime,
    "/interval": _interval,
    "/feeds": _feeds,
    "/reload": _reload,
}