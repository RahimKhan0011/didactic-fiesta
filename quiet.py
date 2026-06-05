import time
import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config import get_quiet_config, DATA_DIR

log = logging.getLogger("quiet")

STATE_FILE = DATA_DIR / "quiet_state.json"
MEGUSTA_FILE = DATA_DIR / "megusta_exclusions.json"
_queue = []


def is_quiet() -> bool:
    if _read_manual_toggle():
        return True
    cfg = get_quiet_config()
    if not cfg.get("enabled", False):
        return False
    try:
        tz = ZoneInfo(cfg.get("timezone", "UTC"))
        now = datetime.now(tz)
        start_h, start_m = map(int, str(cfg["start"]).split(":"))
        end_h, end_m = map(int, str(cfg["end"]).split(":"))
        start_min = start_h * 60 + start_m
        end_min = end_h * 60 + end_m
        now_min = now.hour * 60 + now.minute
        if start_min <= end_min:
            return start_min <= now_min < end_min
        else:
            return now_min >= start_min or now_min < end_min
    except Exception as e:
        log.error(f"Quiet hours check failed: {e}")
        return False


def _read_manual_toggle() -> bool:
    if not STATE_FILE.exists():
        return False
    try:
        data = json.loads(STATE_FILE.read_text())
        return data.get("quiet", False)
    except Exception:
        return False


def set_manual_quiet(on: bool):
    STATE_FILE.write_text(json.dumps({"quiet": on, "set_at": time.time()}))
    log.info(f"Manual quiet mode: {'ON' if on else 'OFF'}")


def queue_notification(data: dict):
    _queue.append(data)


def flush_queue() -> list[dict]:
    global _queue
    items = list(_queue)
    _queue = []
    return items


def get_queue_size() -> int:
    return len(_queue)


def build_summary(items: list[dict]) -> str:
    if not items:
        return ""
    race = [i for i in items if i.get("mode") == "race"]
    content = [i for i in items if i.get("mode") == "content"]

    lines = [f"📋 Quiet Mode Summary ({len(items)} matches)\n"]

    if race:
        lines.append(f"🏁 Race: {len(race)}")
        tiers = {}
        for r in race:
            t = r.get("tier", "none")
            tiers[t] = tiers.get(t, 0) + 1
        for t, c in sorted(tiers.items()):
            lines.append(f"  {t}: {c}")
        lines.append("")

    if content:
        lines.append(f"📺 Content: {len(content)}")
        for c in content[:10]:
            lines.append(f"  {c.get('title', '?')[:60]}")
        if len(content) > 10:
            lines.append(f"  ...and {len(content) - 10} more")

    return "\n".join(lines)


def get_megusta_exclusions() -> list[dict]:
    if not MEGUSTA_FILE.exists():
        return []
    try:
        data = json.loads(MEGUSTA_FILE.read_text())
        now = time.time()
        active = [e for e in data if e.get("expires", 0) > now]
        return active
    except Exception:
        return []


def add_megusta_exclusion(name: str, season: int | None, episode: int | None, hours: int):
    data = get_megusta_exclusions()
    data.append({
        "name": name,
        "season": season,
        "episode": episode,
        "expires": time.time() + (hours * 3600),
        "added": time.time(),
    })
    MEGUSTA_FILE.write_text(json.dumps(data))


def remove_megusta_exclusion(name: str) -> bool:
    data = get_megusta_exclusions()
    filtered = [e for e in data if e.get("name", "").lower() != name.lower()]
    if len(filtered) == len(data):
        return False
    MEGUSTA_FILE.write_text(json.dumps(filtered))
    return True