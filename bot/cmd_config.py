import config


def _config(args: str) -> str:
    groups = config.get_groups()
    alerts = config.get_tier_alerts()
    shows = config.get_shows()
    movies = config.get_movies()
    profiles = config.get_profiles()

    return (
        f"⚙️ <b>Config Overview</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📡 Feeds: {len(config.get_feeds())}\n"
        f"🎯 Profiles: {len(profiles)}\n"
        f"📺 Shows: {len(shows)}\n"
        f"🎬 Movies: {len(movies)}\n\n"
        f"🚫 Banned: {', '.join(groups.get('banned', []))}\n"
        f"🏠 Internal: {', '.join(groups.get('internal', []))}\n\n"
        f"Tier alerts:\n"
        f"  tier1: {'🟢' if alerts.get('tier1', True) else '🔴'}\n"
        f"  tier2: {'🟢' if alerts.get('tier2', True) else '🔴'}\n"
        f"  tier3: {'🟢' if alerts.get('tier3', True) else '🔴'}\n\n"
        f"Edit via:\n"
        f"/addshow /rmshow — shows\n"
        f"/ban /unban — groups\n"
        f"/addgroup — add to tier\n"
        f"/tier2 /tier3 — toggle alerts"
    )


def _profiles(args: str) -> str:
    profiles = config.get_profiles()
    if not profiles:
        return "No profiles configured"
    lines = ["🎯 <b>Active Profiles</b>\n"]
    for name, prof in profiles.items():
        mode = prof.get("mode", "?")
        emoji = "🏁" if mode == "race" else "📺"
        desc = prof.get("desc", name)
        rule = prof.get("rule", "")
        exclude = prof.get("exclude", "")
        max_age = prof.get("max_age", "")
        tmdb = "✅" if prof.get("tmdb", False) else "❌"

        lines.append(f"{emoji} <b>{desc}</b> <code>[{name}]</code>")
        lines.append(f"   📝 {rule}")
        if exclude:
            lines.append(f"   ❌ {exclude}")
        if max_age:
            lines.append(f"   ⏱ {max_age}m")
        lines.append(f"   🎬 TMDB: {tmdb}")
        lines.append("")
    return "\n".join(lines)


HANDLERS = {
    "/config": _config,
    "/profiles": _profiles,
}