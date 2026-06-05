import time
import logging
import threading
import requests

import config

log = logging.getLogger("bot")

API = "https://api.telegram.org/bot{token}/{method}"
_offset = 0
_running = True
_start_time = time.time()
_pending = {}


def get_start_time():
    return _start_time


def get_pending():
    return _pending


def start_polling():
    t = threading.Thread(target=_poll_loop, daemon=True)
    t.start()
    log.info("Bot command polling started")
    _register_commands()
    return t


def stop_polling():
    global _running
    _running = False


def _register_commands():
    url = API.format(token=config.BOT_TOKEN, method="setMyCommands")
    commands = [
        {"command": "help", "description": "Show all commands"},
        {"command": "commands", "description": "Show all commands"},
        {"command": "status", "description": "Monitor status"},
        {"command": "stats", "description": "Database statistics"},
        {"command": "quiet", "description": "Mute notifications"},
        {"command": "loud", "description": "Resume notifications"},
        {"command": "track", "description": "Track episodes — /track ShowName"},
        {"command": "untrack", "description": "Stop tracking — /untrack ShowName"},
        {"command": "addshow", "description": "Add to watchlist — /addshow az ShowName"},
        {"command": "rmshow", "description": "Remove — /rmshow az ShowName"},
        {"command": "show", "description": "Episode status — /show ShowName"},
        {"command": "shows", "description": "Tracked shows + watchlists"},
        {"command": "recent", "description": "Recent matches"},
        {"command": "profiles", "description": "List active profiles"},
        {"command": "tiers", "description": "Group tier assignments"},
        {"command": "tier2", "description": "Toggle tier2 alerts"},
        {"command": "tier3", "description": "Toggle tier3 alerts"},
        {"command": "ban", "description": "Ban a group"},
        {"command": "unban", "description": "Unban a group"},
        {"command": "addgroup", "description": "Add group to a tier"},
        {"command": "patterns", "description": "Group activity patterns"},
        {"command": "groups", "description": "All groups seen in DB"},
        {"command": "search", "description": "Search DB by title"},
        {"command": "dupes", "description": "Recent duplicates"},
        {"command": "missing", "description": "All missing episodes"},
        {"command": "forecast", "description": "Expected group activity"},
        {"command": "interval", "description": "Current check interval"},
        {"command": "feeds", "description": "List configured feeds"},
        {"command": "reload", "description": "Reload config"},
        {"command": "uptime", "description": "Bot uptime"},
        {"command": "ping", "description": "Check if alive"},
        {"command": "config", "description": "View config overview"},
        {"command": "addmovie", "description": "Add movie to watchlist — /addmovie az MovieName"},
        {"command": "rmmovie", "description": "Remove movie — /rmmovie az MovieName"},
        {"command": "addshow", "description": "Add show — /addshow az|tl|all ShowName"},
        {"command": "addmovie", "description": "Add movie — /addmovie az|tl|all MovieName"},
        {"command": "movies", "description": "Movie watchlists with TMDB/IMDb info"},
        {"command": "exclude", "description": "View/add excludes — /exclude exc.shows name"},
        {"command": "unexclude", "description": "Remove exclude — /unexclude exc.shows name"},
        {"command": "get", "description": "Get torrent details — /get ID"},        {"command": "mexclude", "description": "MeGusta exclusion — /mexclude Show S01 24h"},
        {"command": "minclude", "description": "Remove MeGusta exclusion"},
        {"command": "exclude", "description": "View/add excludes"},
        {"command": "unexclude", "description": "Remove exclude"},
        {"command": "get", "description": "Torrent details — /get ID"},
    ]
    try:
        requests.post(url, json={"commands": commands}, timeout=10)
    except Exception as e:
        log.error(f"Failed to register commands: {e}")


def _poll_loop():
    global _offset
    while _running:
        try:
            updates = _get_updates()
            for update in updates:
                _offset = update["update_id"] + 1
                if "callback_query" in update:
                    _handle_callback(update["callback_query"])
                elif "message" in update:
                    _handle_update(update)
        except Exception as e:
            log.error(f"Polling error: {e}")
        time.sleep(2)


def _get_updates() -> list:
    url = API.format(token=config.BOT_TOKEN, method="getUpdates")
    try:
        r = requests.get(url, params={
            "offset": _offset, "timeout": 10,
            "allowed_updates": '["message","callback_query"]'
        }, timeout=15)
        if r.status_code == 200:
            return r.json().get("result", [])
    except Exception:
        pass
    return []


def _handle_update(update: dict):
    msg = update.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = msg.get("text", "").strip()

    if not chat_id or not text:
        return
    if chat_id not in config.CHAT_IDS:
        return
    if not text.startswith("/"):
        return

    parts = text.split(maxsplit=1)
    cmd = parts[0].lower().split("@")[0]
    args = parts[1] if len(parts) > 1 else ""

    from bot.cmd_help import HANDLERS as h1
    from bot.cmd_monitor import HANDLERS as h2
    from bot.cmd_quiet import HANDLERS as h3
    from bot.cmd_shows import HANDLERS as h4
    from bot.cmd_groups import HANDLERS as h5
    from bot.cmd_search import HANDLERS as h6
    from bot.cmd_patterns import HANDLERS as h7
    from bot.cmd_config import HANDLERS as h8

    all_h = {}
    for h in [h1, h2, h3, h4, h5, h6, h7, h8]:
        all_h.update(h)

    handler = all_h.get(cmd)
    if handler:
        try:
            response = handler(args)
            if response:
                if isinstance(response, tuple):
                    if len(response) == 4 and response[0] == "PHOTO":
                        send_photo(chat_id, response[1], response[2], response[3])
                    elif len(response) == 2:
                        reply(chat_id, response[0], response[1])
                    else:
                        reply(chat_id, str(response))
                else:
                    reply(chat_id, response)
        except Exception as e:
            log.error(f"Command error [{cmd}]: {e}")
            reply(chat_id, f"❌ Error: {e}")
    else:
        reply(chat_id, f"Unknown: {cmd}\n/commands for full list")


def _handle_callback(cb: dict):
    cb_id = cb.get("id", "")
    chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
    data = cb.get("data", "")

    if chat_id not in config.CHAT_IDS:
        answer_callback(cb_id, "Unauthorized")
        return

    try:
        from bot.cmd_shows import handle_callback
        result = handle_callback(chat_id, data)
        if result:
            answer_callback(cb_id, result.get("answer", "Done"))
            if result.get("text"):
                reply(chat_id, result["text"])
        else:
            answer_callback(cb_id, "Done")
    except Exception as e:
        log.error(f"Callback error [{data}]: {e}")
        answer_callback(cb_id, f"Error: {e}")


def answer_callback(cb_id: str, text: str = ""):
    url = API.format(token=config.BOT_TOKEN, method="answerCallbackQuery")
    try:
        requests.post(url, json={"callback_query_id": cb_id, "text": text[:200]}, timeout=5)
    except Exception:
        pass


def reply(chat_id: str, text: str, buttons: dict | None = None):
    if len(text) > 4096:
        chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
        for chunk in chunks:
            _send_reply(chat_id, chunk, buttons)
            time.sleep(0.3)
    else:
        _send_reply(chat_id, text, buttons)


def _send_reply(chat_id: str, text: str, buttons: dict | None = None):
    url = API.format(token=config.BOT_TOKEN, method="sendMessage")
    payload = {
        "chat_id": chat_id, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": True
    }
    if buttons:
        payload["reply_markup"] = buttons
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        log.error(f"Reply failed: {e}")

def send_photo(chat_id: str, photo_url: str, caption: str, buttons: dict | None = None):
    url = API.format(token=config.BOT_TOKEN, method="sendPhoto")
    if len(caption) > 1024:
        caption = caption[:1020] + "..."
    payload = {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML",
    }
    if buttons:
        payload["reply_markup"] = buttons
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            log.error(f"Photo send failed: {r.text[:200]}")
            reply(chat_id, caption, buttons)
    except Exception as e:
        log.error(f"Photo send error: {e}")
        reply(chat_id, caption, buttons)

def save_yaml(filename: str, data: dict):
    import yaml

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
    path = config.CONFIG_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    config.reload_yaml()