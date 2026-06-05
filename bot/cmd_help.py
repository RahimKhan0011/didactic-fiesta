def _start(args: str) -> str:
    return "🏴‍☠️ Torrent Monitor active.\n/commands for full list"


def _help(args: str) -> str:
    return (
        "📖 <b>Torrent Monitor — Commands</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📡 <b>Monitor</b>\n"
        "/status — status + quiet mode\n"
        "/stats — database numbers\n"
        "/ping — alive check\n"
        "/uptime — how long running\n"
        "/interval — check interval info\n"
        "/feeds — RSS feeds list\n"
        "/reload — reload config\n"
        "/config — config overview\n\n"
        "🔇 <b>Quiet Mode</b>\n"
        "/quiet — mute alerts\n"
        "/loud — unmute + summary\n\n"
        "📺 <b>Show Tracking</b>\n"
        "/track ShowName — track episodes\n"
        "/untrack ShowName — stop tracking\n"
        "/show ShowName — episode status\n"
        "/shows — tracked + watchlists\n"
        "/missing — missing episodes\n\n"
        "📋 <b>Watchlists</b>\n"
        "/addshow az|tl|all ShowName — add show\n"
        "/rmshow az|tl|all ShowName — remove show\n\n"
        "🎬 <b>Movies</b>\n"
        "/movies — movie watchlists\n"
        "/addmovie az|tl|all MovieName — add movie\n"
        "/rmmovie az|tl|all MovieName — remove movie\n\n"
        "🔍 <b>Search</b>\n"
        "/search keyword — search DB\n"
        "/search tl|az keyword — tracker search\n"
        "/get ID — full torrent details\n"
        "/recent — last 6h\n"
        "/dupes — recent duplicates\n\n"
        "🏁 <b>Groups</b>\n"
        "/profiles — active profiles\n"
        "/tiers — tier assignments\n"
        "/tier2 /tier3 — toggle alerts\n"
        "/ban /unban GroupName\n"
        "/addgroup tier1 GroupName\n"
        "/groups — DB group stats\n\n"
        "🚫 <b>Excludes</b>\n"
        "/exclude — view lists\n"
        "/exclude exc.shows name — add\n"
        "/unexclude exc.shows name — remove\n\n"
        "🤖 <b>MeGusta</b>\n"
        "/mexclude — view exclusions\n"
        "/mexclude Show S01 24h — exclude\n"
        "/minclude ShowName — remove\n\n"
        "📊 <b>Patterns</b>\n"
        "/patterns — group activity\n"
        "/forecast — active now\n"
    )


HANDLERS = {
    "/start": _start,
    "/help": _help,
    "/commands": _help,
}