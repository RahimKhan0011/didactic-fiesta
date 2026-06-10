import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
CONFIG_DIR = BASE_DIR / "config"

DB_MAIN = DATA_DIR / "torrents.db"
DB_HISTORY = DATA_DIR / "history.db"
DB_PATTERNS = DATA_DIR / "patterns.db"


def _env(key, default=""):
    return os.getenv(key, default)


BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
CHAT_IDS = [c.strip() for c in _env("TELEGRAM_CHAT_IDS", "").split(",") if c.strip()]
TMDB_API_KEY = _env("TMDB_API_KEY")
TVDB_API_KEY = os.getenv("TVDB_API_KEY", "")
LOG_LEVEL = _env("LOG_LEVEL", "INFO").upper()
BASE_INTERVAL = int(_env("BASE_INTERVAL", "60"))
TIMEZONE = _env("TIMEZONE", "UTC")
STARTUP_LOOKBACK = int(_env("STARTUP_LOOKBACK", "600"))
AUTO_DELETE_NOTIFICATIONS = os.getenv("AUTO_DELETE_NOTIFICATIONS", "false").lower() in ("true", "1", "yes")
AUTO_DELETE_HOURS = int(os.getenv("AUTO_DELETE_HOURS", "24"))

_cache = {}


def _parse_csv(val) -> list[str]:
    if isinstance(val, list):
        return [str(v).strip() for v in val if str(v).strip()]
    if isinstance(val, str):
        return [v.strip() for v in val.split(",") if v.strip()]
    return []


def _load_yaml_file(name: str) -> dict:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def _save_yaml_file(name: str, data: dict):
    class FlowList(list):
        pass

    def flow_representer(dumper, data):
        return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)

    yaml.add_representer(FlowList, flow_representer)

    def convert(obj):
        if isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            if all(isinstance(i, (str, int, float)) for i in obj):
                return FlowList(obj)
            return [convert(i) for i in obj]
        return obj

    data = convert(data)
    path = CONFIG_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def load_all() -> dict:
    global _cache
    merged = {}
    for fname in ["definitions.yaml", "groups.yaml", "watchlists.yaml",
                   "excludes.yaml", "profiles.yaml", "settings.yaml"]:
        data = _load_yaml_file(fname)
        if fname == "groups.yaml":
            merged["groups"] = data
        elif fname == "watchlists.yaml":
            merged["watchlists"] = data
        elif fname == "excludes.yaml":
            merged["exclude"] = data
        elif fname == "profiles.yaml":
            merged["profiles"] = data
        else:
            merged.update(data)
    _cache = merged
    return merged


def load_yaml() -> dict:
    if _cache:
        return _cache
    return load_all()


def reload_yaml():
    global _cache
    _cache = {}
    return load_all()


def get_feeds() -> list[dict]:
    feeds = []
    i = 1
    while True:
        val = _env(f"RSS_FEED_{i}")
        if not val:
            break
        parts = val.split("|")
        if len(parts) >= 3:
            feeds.append({"name": parts[0].strip(), "url": parts[1].strip(), "tracker": parts[2].strip()})
        elif len(parts) == 2:
            feeds.append({"name": parts[0].strip(), "url": parts[1].strip(), "tracker": "tl"})
        else:
            feeds.append({"name": f"Feed {i}", "url": val.strip(), "tracker": "tl"})
        i += 1
    return feeds


def get_definitions() -> dict[str, list[str]]:
    data = load_yaml()
    defs = {}
    for section in ["quality", "source", "codec", "category", "exclude", "tracker"]:
        block = data.get(section, {})
        if isinstance(block, dict):
            for key, val in block.items():
                defs[key] = _parse_csv(val)
    return defs


def get_groups() -> dict[str, list[str]]:
    data = load_yaml()
    raw = data.get("groups", {})
    result = {}
    for key, val in raw.items():
        result[key] = _parse_csv(val)
    return result


def get_watchlists() -> dict[str, list[str]]:
    data = load_yaml()
    raw = data.get("watchlists", {})
    result = {}
    if isinstance(raw, dict):
        for key, val in raw.items():
            if isinstance(val, list):
                result[key] = [str(v).strip() for v in val if str(v).strip()]
            else:
                result[key] = _parse_csv(val)
    return result


def get_profiles() -> dict[str, dict]:
    return load_yaml().get("profiles", {})


def get_banned_groups() -> list[str]:
    return get_groups().get("banned", [])


def get_internal_groups() -> list[str]:
    return get_groups().get("internal", [])


def get_ignore_categories() -> list[str]:
    data = load_yaml()
    return _parse_csv(data.get("ignore_categories", ""))


def get_emergency_keywords() -> list[str]:
    data = load_yaml()
    return _parse_csv(data.get("emergency_keywords", ""))


def get_tier_alerts() -> dict:
    return load_yaml().get("tier_alerts", {"tier1": True, "tier2": True, "tier3": True})


def get_quiet_config() -> dict:
    return load_yaml().get("quiet_hours", {"enabled": False})


def get_race_groups() -> dict[str, list[str]]:
    groups = get_groups()
    return {k: v for k, v in groups.items() if k.startswith("tier")}


def get_smart_interval() -> dict:
    data = load_yaml()
    si = data.get("smart_interval", {})
    result = {
        "peak_multiplier": si.get("peak_multiplier", 0.5),
        "dead_multiplier": si.get("dead_multiplier", 2.0),
        "tier1_burst": si.get("tier1_burst", 20),
        "cooldown_multiplier": si.get("cooldown_multiplier", 1.5),
        "cooldown_after_empty": si.get("cooldown_after_empty", 3),
    }
    peak = si.get("peak_hours", "16-23")
    dead = si.get("dead_hours", "2-7")
    if isinstance(peak, str) and "-" in peak:
        p = peak.split("-")
        result["peak_hours"] = [int(p[0]), int(p[1])]
    elif isinstance(peak, list):
        result["peak_hours"] = peak
    else:
        result["peak_hours"] = [16, 23]
    if isinstance(dead, str) and "-" in dead:
        d = dead.split("-")
        result["dead_hours"] = [int(d[0]), int(d[1])]
    elif isinstance(dead, list):
        result["dead_hours"] = dead
    else:
        result["dead_hours"] = [2, 7]
    return result


def get_shows() -> list[str]:
    wl = get_watchlists()
    all_shows = []
    for key, val in wl.items():
        if "shows" in key.lower():
            all_shows.extend(val)
    return all_shows


def get_movies() -> list[str]:
    wl = get_watchlists()
    all_movies = []
    for key, val in wl.items():
        if "movies" in key.lower():
            all_movies.extend(val)
    return all_movies


def validate():
    errors = []
    if not BOT_TOKEN or "your_" in BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN not set")
    if not CHAT_IDS:
        errors.append("TELEGRAM_CHAT_IDS not set")
    if not TMDB_API_KEY:
        errors.append("TMDB_API_KEY not set (optional)")
    feeds = get_feeds()
    if not feeds:
        errors.append("No RSS_FEED_* in .env")
    if not CONFIG_DIR.exists():
        errors.append(f"Config dir not found: {CONFIG_DIR}")
    return errors