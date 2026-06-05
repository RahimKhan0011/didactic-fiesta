import re
import time
import sqlite3
import config
from bot.polling import save_yaml


def _load_settings():
    return config._load_yaml_file("settings.yaml")


def _load_groups():
    return config._load_yaml_file("groups.yaml")


def _tiers(args: str) -> str:
    groups = config.get_groups()
    alerts = config.get_tier_alerts()
    tier_map = {"tier1": "🥇", "tier2": "🥈", "tier3": "🥉"}
    lines = ["🏆 <b>Group Tiers</b>\n"]

    for tier in ["tier1", "tier2", "tier3"]:
        if tier in groups:
            emoji = tier_map.get(tier, "")
            alert = "🟢" if alerts.get(tier, True) else "🔴"
            lines.append(f"{emoji} <b>{tier.upper()}</b> {alert}")
            lines.append(f"   {', '.join(groups[tier])}")
            lines.append("")

    if "banned" in groups:
        lines.append("🚫 <b>BANNED</b>")
        lines.append(f"   {', '.join(groups['banned'])}")
        lines.append("")

    if "internal" in groups:
        lines.append("🏠 <b>INTERNAL</b>")
        lines.append(f"   {', '.join(groups['internal'])}")

    for key in groups:
        if key not in ["tier1", "tier2", "tier3", "banned", "internal"]:
            lines.append(f"\n🏷 <b>{key.upper()}</b>")
            lines.append(f"   {', '.join(groups[key])}")

    return "\n".join(lines)


def _tier2(args: str) -> str:
    return _toggle_tier("tier2")


def _tier3(args: str) -> str:
    return _toggle_tier("tier3")


def _toggle_tier(tier: str) -> str:
    data = _load_settings()
    if "tier_alerts" not in data:
        data["tier_alerts"] = {"tier1": True, "tier2": True, "tier3": True}
    current = data["tier_alerts"].get(tier, True)
    data["tier_alerts"][tier] = not current
    save_yaml("settings.yaml", data)
    state = "🟢 ON" if not current else "🔴 OFF"
    return f"{tier.upper()} alerts: {state}"


def _ban(args: str) -> str:
    if not args:
        return "Usage: /ban GroupName"
    group = args.strip()
    data = _load_groups()
    banned = config._parse_csv(data.get("banned", ""))
    if group in banned:
        return f"Already banned: {group}"
    banned.append(group)
    data["banned"] = ", ".join(banned)
    save_yaml("groups.yaml", data)
    return f"🚫 Banned: {group}"


def _unban(args: str) -> str:
    if not args:
        return "Usage: /unban GroupName"
    group = args.strip()
    data = _load_groups()
    banned = config._parse_csv(data.get("banned", ""))
    matched = [g for g in banned if g.lower() == group.lower()]
    if not matched:
        return f"Not banned: {group}"
    for m in matched:
        banned.remove(m)
    data["banned"] = ", ".join(banned)
    save_yaml("groups.yaml", data)
    return f"✅ Unbanned: {group}"


def _addgroup(args: str) -> str:
    if not args:
        return "Usage: /addgroup tier1 GroupName"
    parts = args.strip().split(maxsplit=1)
    if len(parts) < 2:
        return "Usage: /addgroup tier1 GroupName"
    tier = parts[0].lower()
    group = parts[1].strip()
    data = _load_groups()
    if tier not in data:
        return f"Invalid: {tier}\nAvailable: {', '.join(data.keys())}"
    existing = config._parse_csv(data.get(tier, ""))
    if group in existing:
        return f"Already in {tier}: {group}"
    existing.append(group)
    data[tier] = ", ".join(existing)
    save_yaml("groups.yaml", data)
    return f"✅ Added {group} to {tier}"


def _groups(args: str) -> str:
    conn = sqlite3.connect(str(config.DB_MAIN))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT parsed_group, COUNT(*) as cnt, MAX(pub_timestamp) as last_seen
        FROM torrents
        WHERE parsed_group IS NOT NULL AND parsed_group != ''
        GROUP BY parsed_group ORDER BY cnt DESC LIMIT 40
    """).fetchall()
    conn.close()
    if not rows:
        return "No groups in DB yet"
    lines = ["👤 <b>Groups Seen</b> (top 40)\n"]
    for r in rows:
        ago = ""
        if r["last_seen"]:
            h = (time.time() - r["last_seen"]) / 3600
            if h < 1:
                ago = f"{int(h * 60)}m ago"
            elif h < 24:
                ago = f"{int(h)}h ago"
            else:
                ago = f"{int(h / 24)}d ago"
        lines.append(f"  <code>{r['parsed_group']}</code> — {r['cnt']} | {ago}")
    return "\n".join(lines)


def _exclude(args: str) -> str:
    if not args:
        data = config._load_yaml_file("excludes.yaml")
        lines = ["❌ <b>Exclude Lists</b>\n"]
        for key, val in data.items():
            items = config._parse_csv(val)
            lines.append(f"<b>{key}:</b>")
            lines.append(f"  {', '.join(items)}")
            lines.append("")
        return "\n".join(lines)

    parts = args.strip().split(maxsplit=1)
    if len(parts) < 2:
        return "Usage: /exclude exc.shows jimmy kimmel"

    exc_key = parts[0].strip()
    value = parts[1].strip()

    data = config._load_yaml_file("excludes.yaml")
    existing = config._parse_csv(data.get(exc_key, ""))

    if value.lower() in [e.lower() for e in existing]:
        return f"Already in {exc_key}: {value}"

    existing.append(value)
    data[exc_key] = ", ".join(existing)
    save_yaml("excludes.yaml", data)

    return f"✅ Added to {exc_key}: {value}"


def _unexclude(args: str) -> str:
    if not args:
        return "Usage: /unexclude exc.shows jimmy kimmel"

    parts = args.strip().split(maxsplit=1)
    if len(parts) < 2:
        return "Usage: /unexclude exc.shows jimmy kimmel"

    exc_key = parts[0].strip()
    value = parts[1].strip()

    data = config._load_yaml_file("excludes.yaml")
    existing = config._parse_csv(data.get(exc_key, ""))

    matched = [e for e in existing if e.lower() == value.lower()]
    if not matched:
        return f"Not in {exc_key}: {value}"

    for m in matched:
        existing.remove(m)

    data[exc_key] = ", ".join(existing)
    save_yaml("excludes.yaml", data)

    return f"✅ Removed from {exc_key}: {value}"


def _mexclude(args: str) -> str:
    if not args:
        from quiet import get_megusta_exclusions
        exclusions = get_megusta_exclusions()
        if not exclusions:
            return (
                "No MeGusta exclusions active\n\n"
                "Usage:\n"
                "/mexclude ShowName S01 24h\n"
                "/mexclude ShowName S01E03 12h\n"
                "/mexclude ShowName 48h"
            )
        lines = ["🤖 <b>MeGusta Exclusions</b>\n"]
        for e in exclusions:
            remaining = int((e["expires"] - time.time()) / 3600)
            season = f" S{e['season']:02d}" if e.get("season") is not None else ""
            episode = f"E{e['episode']:02d}" if e.get("episode") is not None else ""
            lines.append(f"  • {e['name']}{season}{episode} ({remaining}h left)")
        return "\n".join(lines)

    time_match = re.search(r'(\d+)h$', args)
    if not time_match:
        return "Usage: /mexclude ShowName S01 24h"

    hours = int(time_match.group(1))
    rest = args[:time_match.start()].strip()

    season = None
    episode = None

    se_match = re.search(r'\bS(\d{1,2})(?:E(\d{1,2}))?\s*$', rest, re.IGNORECASE)
    if se_match:
        season = int(se_match.group(1))
        if se_match.group(2):
            episode = int(se_match.group(2))
        rest = rest[:se_match.start()].strip()

    name = rest.strip()
    if not name:
        return "Usage: /mexclude ShowName S01 24h"

    from quiet import add_megusta_exclusion
    add_megusta_exclusion(name, season, episode, hours)

    season_str = f" S{season:02d}" if season is not None else ""
    episode_str = f"E{episode:02d}" if episode is not None else ""
    return f"🤖 MeGusta excluded: {name}{season_str}{episode_str} for {hours}h"


def _minclude(args: str) -> str:
    if not args:
        return "Usage: /minclude ShowName"

    from quiet import remove_megusta_exclusion
    if remove_megusta_exclusion(args.strip()):
        return f"✅ Removed MeGusta exclusion: {args.strip()}"
    return f"Not found: {args.strip()}"


HANDLERS = {
    "/tiers": _tiers,
    "/tier2": _tier2,
    "/tier3": _tier3,
    "/ban": _ban,
    "/unban": _unban,
    "/addgroup": _addgroup,
    "/groups": _groups,
    "/exclude": _exclude,
    "/unexclude": _unexclude,
    "/mexclude": _mexclude,
    "/minclude": _minclude,
}