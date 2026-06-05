import re
import math
import requests

import db
import config
import tracker
import tmdb
from bot.polling import save_yaml


TRACKER_MAP = {
    "tl": {"shows": "wl.tl_shows", "movies": "wl.tl_movies", "name": "TorrentLeech"},
    "az": {"shows": "wl.az_shows", "movies": "wl.az_movies", "name": "AvistaZ"},
    "ar": {"shows": "wl.ar_shows", "movies": "wl.ar_movies", "name": "AlphaRatio"},
    "huno": {"shows": "wl.huno_shows", "movies": "wl.huno_movies", "name": "HUNO"},
    "fl": {"shows": "wl.fl_shows", "movies": "wl.fl_movies", "name": "FileList"},
    "erai": {"shows": "wl.erai_shows", "movies": "wl.erai_movies", "name": "Erai-raws"},
    "ipt": {"shows": "wl.ipt_shows", "movies": "wl.ipt_movies", "name": "IPTorrents"},
}


def _get_tracker(trk: str):
    return TRACKER_MAP.get((trk or "").lower())


def _tmdb_search_tv(name: str):
    if not config.TMDB_API_KEY:
        return None
    try:
        r = requests.get(
            "https://api.themoviedb.org/3/search/tv",
            params={"api_key": config.TMDB_API_KEY, "query": name},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        results = r.json().get("results", [])
        if not results:
            return None

        hit = results[0]
        detail = requests.get(
            f"https://api.themoviedb.org/3/tv/{hit['id']}",
            params={"api_key": config.TMDB_API_KEY},
            timeout=10,
        ).json()

        return {
            "name": hit.get("name", name),
            "tmdb_id": hit["id"],
            "rating": hit.get("vote_average", 0),
            "overview": hit.get("overview", "") or "",
            "poster": f"https://image.tmdb.org/t/p/w500{hit['poster_path']}" if hit.get("poster_path") else "",
            "seasons": detail.get("number_of_seasons", 0),
            "status": detail.get("status", ""),
        }
    except Exception:
        return None


def _tmdb_search_movie(name: str, year: int | None = None):
    if not config.TMDB_API_KEY:
        return None
    try:
        params = {"api_key": config.TMDB_API_KEY, "query": name}
        if year:
            params["year"] = year

        r = requests.get(
            "https://api.themoviedb.org/3/search/movie",
            params=params,
            timeout=10,
        )
        if r.status_code != 200:
            return None

        results = r.json().get("results", [])
        if not results:
            return None

        hit = results[0]
        release_date = hit.get("release_date", "") or ""
        movie_year = int(release_date[:4]) if len(release_date) >= 4 else None

        imdb_id = ""
        try:
            ext = requests.get(
                f"https://api.themoviedb.org/3/movie/{hit['id']}/external_ids",
                params={"api_key": config.TMDB_API_KEY},
                timeout=10,
            ).json()
            imdb_id = ext.get("imdb_id", "")
        except Exception:
            pass

        return {
            "title": hit.get("title", name),
            "tmdb_id": hit["id"],
            "rating": hit.get("vote_average", 0),
            "overview": hit.get("overview", "") or "",
            "poster": f"https://image.tmdb.org/t/p/w500{hit['poster_path']}" if hit.get("poster_path") else "",
            "year": movie_year,
            "release_date": release_date,
            "imdb_id": imdb_id,
        }
    except Exception:
        return None


def _track(args: str) -> str:
    if not args:
        return (
            "Usage: /track ShowName\n"
            "Example: /track Doctor on the Edge\n\n"
            "Tracks episodes in DB for /show"
        )
    return tracker.add_show(args.strip())


def _untrack(args: str) -> str:
    if not args:
        return "Usage: /untrack ShowName\nExample: /untrack Doctor on the Edge"
    return tracker.remove_show(args.strip())


def _show(args: str) -> str:
    if not args:
        return "Usage: /show ShowName\nExample: /show Doctor on the Edge"
    return tracker.get_show_status(args.strip())


def _shows(args: str) -> str:
    tracked = db.get_all_tracked_shows()
    lines = []

    if tracked:
        lines.append("📺 <b>Tracked Shows</b>\n")
        for s in tracked:
            if s.latest_episode:
                status = f"S{s.latest_season:02d}E{s.latest_episode:02d}"
            else:
                status = "waiting"

            next_str = ""
            try:
                info = tmdb.search_tv(s.show_name)
                if info:
                    next_ep = tmdb.get_next_episode(info["tmdb_id"])
                    if next_ep and next_ep.get("next_air_date"):
                        from datetime import datetime
                        air = datetime.strptime(next_ep["next_air_date"], "%Y-%m-%d")
                        diff = (air - datetime.now()).days
                        if diff == 0:
                            next_str = " | Next TODAY"
                        elif diff == 1:
                            next_str = " | Next TOMORROW"
                        elif 0 < diff <= 14:
                            next_str = f" | Next in {diff}d"
                    elif next_ep and next_ep.get("status") in ("Ended", "Canceled"):
                        next_str = f" | {next_ep['status']}"
            except Exception:
                pass

            lines.append(f"  • {s.show_name} — {status}{next_str}")
    else:
        lines.append("📺 No shows tracked")

    wl = config.get_watchlists()
    show_wl = []
    for key, items in wl.items():
        if not items:
            continue
        for trk_code, trk_info in TRACKER_MAP.items():
            if trk_info["shows"] == key:
                for item in items:
                    show_wl.append(f"  • [{trk_code.upper()}] {item}")

    if show_wl:
        lines.append("\n<b>Show Watchlists:</b>")
        lines.extend(show_wl)

    return "\n".join(lines)


def _movies(args: str) -> str:
    wl = config.get_watchlists()
    lines = ["🎬 <b>Movie Watchlists</b>\n"]
    found = False

    for trk_code, trk_info in TRACKER_MAP.items():
        key = trk_info["movies"]
        items = wl.get(key, [])
        if items:
            found = True
            lines.append(f"<b>{trk_info['name']}:</b>")
            for movie in items:
                movie_name = re.sub(r"\s+\d{4}$", "", movie).strip()
                year_match = re.search(r"\s+(\d{4})$", movie)
                year = int(year_match.group(1)) if year_match else None

                info = _tmdb_search_movie(movie_name, year)
                if info:
                    rating = f"⭐ {info['rating']}/10" if info.get("rating") else ""
                    imdb = f" | IMDb: {info['imdb_id']}" if info.get("imdb_id") else ""
                    lines.append(f"  • {movie} {rating}{imdb}")
                else:
                    lines.append(f"  • {movie}")
            lines.append("")

    if not found:
        lines.append("No movies in watchlists")
        lines.append("/addmovie tl MovieName — add movie")

    return "\n".join(lines)


def _missing(args: str) -> str:
    tracked = db.get_all_tracked_shows()
    if not tracked:
        return "No shows tracked"

    lines = ["❌ <b>Missing Episodes</b>\n"]
    found = False

    for s in tracked:
        episodes = db.get_show_episodes(s.show_name)
        seasons = {}
        for ep in episodes:
            seasons.setdefault(ep.season, []).append(ep.episode)

        for sn, eps in sorted(seasons.items()):
            miss = tracker.find_missing_episodes(s.show_name, sn)
            if miss:
                found = True
                ms = ", ".join(f"E{m:02d}" for m in miss)
                lines.append(f"📺 {s.show_name} S{sn:02d}: {ms}")

    if not found:
        return "✅ No missing episodes"

    return "\n".join(lines)


def _addshow(args: str):
    if not args:
        return (
            "Usage: /addshow <tl|az|ar|huno|fl|erai|ipt|all> ShowName\n\n"
            "Examples:\n"
            "  /addshow az The Rookie\n"
            "  /addshow tl From S04\n"
            "  /addshow all Doctor on the Edge S01"
        )

    parts = args.strip().split(maxsplit=1)
    if len(parts) < 2:
        return "Usage: /addshow <tracker|all> ShowName"

    trk = parts[0].lower()
    show = parts[1].strip()

    if trk == "all":
        return _add_show_all_trackers(show)

    trk_info = _get_tracker(trk)
    if not trk_info:
        return "Unknown tracker. Use: tl, az, ar, huno, fl, erai, ipt, or all"

    has_season = bool(re.search(r"\s+[Ss]\d+$", show))
    if has_season:
        return _add_show_direct(trk, show)

    info = _tmdb_search_tv(show)
    if not info or info["seasons"] == 0:
        return _add_show_direct(trk, show)

    buttons = []
    total = info["seasons"]
    per_row = 4
    rows = math.ceil(total / per_row)

    for row_i in range(rows):
        row = []
        for col in range(per_row):
            s = row_i * per_row + col + 1
            if s > total:
                break
            row.append({"text": f"S{s:02d}", "callback_data": f"addshow|{trk}|{show}|S{s:02d}"})
        if row:
            buttons.append(row)

    buttons.append([
        {"text": "📺 All Seasons", "callback_data": f"addshow|{trk}|{show}|ALL"},
        {"text": "❌ Cancel", "callback_data": f"addshow|{trk}|{show}|CANCEL"},
    ])

    tracker_name = trk_info["name"]
    rating = f"⭐ {info['rating']}/10" if info['rating'] else ""
    overview = info.get("overview", "")
    status_str = info.get("status", "")

    text = (
        f"🎬 <b>{info['name']}</b>\n"
        f"{rating}\n"
        f"📺 {total} Seasons | {status_str}\n\n"
        f"{overview}\n\n"
        f"Adding to: <b>{tracker_name}</b>\n"
        f"Pick season:"
    )

    markup = {"inline_keyboard": buttons}

    if info.get("poster"):
        return ("PHOTO", info["poster"], text, markup)
    return (text, markup)


def _add_show_direct(trk: str, show: str) -> str:
    trk_info = _get_tracker(trk)
    if not trk_info:
        return "Unknown tracker"

    key = trk_info["shows"]
    tracker_name = trk_info["name"]

    data = config._load_yaml_file("watchlists.yaml")
    items = data.get(key, [])
    if not isinstance(items, list):
        items = []

    for existing in items:
        if existing.lower() == show.lower():
            return f"Already in {tracker_name}: {show}"

    items.append(show)
    data[key] = items
    save_yaml("watchlists.yaml", data)

    clean = re.sub(r"\s+[Ss]\d+$", "", show).strip()
    track_result = tracker.add_show(clean)

    return f"✅ Added to {tracker_name}: {show}\n📋 {track_result}"


def _add_show_all_trackers(show: str) -> str:
    lines = []
    clean = re.sub(r"\s+[Ss]\d+$", "", show).strip()
    tracked_once = False

    for trk_code, trk_info in TRACKER_MAP.items():
        key = trk_info["shows"]
        tracker_name = trk_info["name"]

        data = config._load_yaml_file("watchlists.yaml")
        items = data.get(key, [])
        if not isinstance(items, list):
            items = []

        already = any(x.lower() == show.lower() for x in items)
        if already:
            lines.append(f"Already in {tracker_name}: {show}")
        else:
            items.append(show)
            data[key] = items
            save_yaml("watchlists.yaml", data)
            lines.append(f"✅ Added to {tracker_name}: {show}")

        if not tracked_once:
            lines.append(f"📋 {tracker.add_show(clean)}")
            tracked_once = True

    return "\n".join(lines)


def _addmovie(args: str):
    if not args:
        return (
            "Usage: /addmovie <tl|az|ar|huno|fl|erai|ipt|all> MovieName\n\n"
            "Examples:\n"
            "  /addmovie az Dune\n"
            "  /addmovie all Enola Holmes 3"
        )

    parts = args.strip().split(maxsplit=1)
    if len(parts) < 2:
        return "Usage: /addmovie <tracker|all> MovieName"

    trk = parts[0].lower()
    movie = parts[1].strip()

    if trk == "all":
        has_year = bool(re.search(r"\s+\d{4}$", movie))
        if has_year:
            return _add_movie_all_trackers(movie)

        info = _tmdb_search_movie(movie)
        if info and info.get("year"):
            return _add_movie_all_trackers(f"{info['title']} {info['year']}")
        return _add_movie_all_trackers(movie)

    trk_info = _get_tracker(trk)
    if not trk_info:
        return "Unknown tracker. Use: tl, az, ar, huno, fl, erai, ipt, or all"

    has_year = bool(re.search(r"\s+\d{4}$", movie))
    if has_year:
        return _add_movie_direct(trk, movie)

    info = _tmdb_search_movie(movie)
    if not info:
        return _add_movie_direct(trk, movie)

    year_suffix = f" {info['year']}" if info.get("year") else ""
    movie_with_year = f"{info['title']}{year_suffix}"
    tracker_name = trk_info["name"]

    buttons = {
        "inline_keyboard": [
            [
                {"text": f"✅ Add: {movie_with_year}", "callback_data": f"addmovie|{trk}|{movie_with_year}|YES"},
                {"text": "❌ Cancel", "callback_data": f"addmovie|{trk}|{movie_with_year}|CANCEL"},
            ],
            [
                {"text": "✅ Add without year", "callback_data": f"addmovie|{trk}|{info['title']}|YES"},
            ],
        ]
    }

    rating = f"⭐ {info['rating']}/10" if info.get("rating") else ""
    overview = info.get("overview", "")
    release = f"📅 {info['release_date']}" if info.get("release_date") else ""
    imdb = f"🎬 IMDb: {info['imdb_id']}" if info.get("imdb_id") else ""

    text = (
        f"🎬 <b>{info['title']}</b>{year_suffix}\n"
        f"{rating}\n"
        f"{release}\n"
        f"{imdb}\n\n"
        f"{overview}\n\n"
        f"Adding to: <b>{tracker_name}</b>"
    )

    if info.get("poster"):
        return ("PHOTO", info["poster"], text, buttons)
    return (text, buttons)


def _add_movie_direct(trk: str, movie: str) -> str:
    trk_info = _get_tracker(trk)
    if not trk_info:
        return "Unknown tracker"

    key = trk_info["movies"]
    tracker_name = trk_info["name"]

    data = config._load_yaml_file("watchlists.yaml")
    items = data.get(key, [])
    if not isinstance(items, list):
        items = []

    for existing in items:
        if existing.lower() == movie.lower():
            return f"Already in {tracker_name}: {movie}"

    items.append(movie)
    data[key] = items
    save_yaml("watchlists.yaml", data)

    return f"✅ Added to {tracker_name} movies: {movie}"


def _add_movie_all_trackers(movie: str) -> str:
    lines = []

    for trk_code, trk_info in TRACKER_MAP.items():
        key = trk_info["movies"]
        tracker_name = trk_info["name"]

        data = config._load_yaml_file("watchlists.yaml")
        items = data.get(key, [])
        if not isinstance(items, list):
            items = []

        already = any(x.lower() == movie.lower() for x in items)
        if already:
            lines.append(f"Already in {tracker_name}: {movie}")
        else:
            items.append(movie)
            data[key] = items
            save_yaml("watchlists.yaml", data)
            lines.append(f"✅ Added to {tracker_name} movies: {movie}")

    return "\n".join(lines)


def _rmshow(args: str) -> str:
    if not args:
        return (
            "Usage: /rmshow <tracker|all> ShowName\n\n"
            "Examples:\n"
            "  /rmshow az Doctor on the Edge S01\n"
            "  /rmshow all From S04"
        )

    parts = args.strip().split(maxsplit=1)
    if len(parts) < 2:
        return "Usage: /rmshow <tracker|all> ShowName"

    trk = parts[0].lower()
    show = parts[1].strip()

    if trk == "all":
        lines = []
        for code in TRACKER_MAP:
            lines.append(_rm_show_single(code, show, skip_untrack=True))
        clean = re.sub(r"\s+[Ss]\d+$", "", show).strip()
        lines.append(f"📋 {tracker.remove_show(clean)}")
        return "\n".join(lines)

    return _rm_show_single(trk, show)


def _rm_show_single(trk: str, show: str, skip_untrack: bool = False) -> str:
    trk_info = _get_tracker(trk)
    if not trk_info:
        return f"Unknown tracker: {trk}"

    key = trk_info["shows"]
    tracker_name = trk_info["name"]

    data = config._load_yaml_file("watchlists.yaml")
    items = data.get(key, [])
    if not isinstance(items, list):
        items = []

    matched = [x for x in items if x.lower() == show.lower()]
    if not matched:
        return f"Not in {tracker_name}: {show}"

    for m in matched:
        items.remove(m)

    data[key] = items
    save_yaml("watchlists.yaml", data)

    if not skip_untrack:
        clean = re.sub(r"\s+[Ss]\d+$", "", show).strip()
        return f"✅ Removed from {tracker_name}: {show}\n📋 {tracker.remove_show(clean)}"

    return f"✅ Removed from {tracker_name}: {show}"


def _rmmovie(args: str) -> str:
    if not args:
        return (
            "Usage: /rmmovie <tracker|all> MovieName\n\n"
            "Examples:\n"
            "  /rmmovie az Dune 2021\n"
            "  /rmmovie all Enola Holmes 3 2026"
        )

    parts = args.strip().split(maxsplit=1)
    if len(parts) < 2:
        return "Usage: /rmmovie <tracker|all> MovieName"

    trk = parts[0].lower()
    movie = parts[1].strip()

    if trk == "all":
        lines = []
        for code in TRACKER_MAP:
            lines.append(_rm_movie_single(code, movie))
        return "\n".join(lines)

    return _rm_movie_single(trk, movie)


def _rm_movie_single(trk: str, movie: str) -> str:
    trk_info = _get_tracker(trk)
    if not trk_info:
        return f"Unknown tracker: {trk}"

    key = trk_info["movies"]
    tracker_name = trk_info["name"]

    data = config._load_yaml_file("watchlists.yaml")
    items = data.get(key, [])
    if not isinstance(items, list):
        items = []

    matched = [x for x in items if x.lower() == movie.lower()]
    if not matched:
        return f"Not in {tracker_name}: {movie}"

    for m in matched:
        items.remove(m)

    data[key] = items
    save_yaml("watchlists.yaml", data)

    return f"✅ Removed from {tracker_name}: {movie}"


def handle_callback(chat_id: str, data: str):
    if data.startswith("addshow|"):
        return _handle_addshow_callback(data)
    if data.startswith("addmovie|"):
        return _handle_addmovie_callback(data)
    return None


def _handle_addshow_callback(data: str):
    parts = data.split("|")
    if len(parts) < 4:
        return {"answer": "Invalid"}

    trk = parts[1]
    show = parts[2]
    choice = parts[3]

    if choice == "CANCEL":
        return {"answer": "Cancelled", "text": "❌ Cancelled"}

    if choice == "ALL":
        result = _add_show_direct(trk, show)
        return {"answer": "Added all seasons", "text": result}

    season = choice
    show_with_season = f"{show} {season}"

    trk_info = _get_tracker(trk)
    if not trk_info:
        return {"answer": "Unknown tracker"}

    key = trk_info["shows"]
    tracker_name = trk_info["name"]

    data_yaml = config._load_yaml_file("watchlists.yaml")
    items = data_yaml.get(key, [])
    if not isinstance(items, list):
        items = []

    for existing in items:
        if existing.lower() == show_with_season.lower():
            clean = re.sub(r"\s+[Ss]\d+$", "", show).strip()
            tracker.add_show(clean)
            return {"answer": "Already exists", "text": f"Already in {tracker_name}: {show_with_season}"}

    items.append(show_with_season)
    data_yaml[key] = items
    save_yaml("watchlists.yaml", data_yaml)

    clean = re.sub(r"\s+[Ss]\d+$", "", show).strip()
    track_result = tracker.add_show(clean)

    return {
        "answer": f"Added {season}",
        "text": f"✅ {tracker_name}: {show_with_season}\n📋 {track_result}"
    }


def _handle_addmovie_callback(data: str):
    parts = data.split("|")
    if len(parts) < 4:
        return {"answer": "Invalid"}

    trk = parts[1]
    movie = parts[2]
    choice = parts[3]

    if choice == "CANCEL":
        return {"answer": "Cancelled", "text": "❌ Cancelled"}

    if choice == "YES":
        result = _add_movie_direct(trk, movie)
        return {"answer": "Added", "text": result}

    return {"answer": "Unknown"}


HANDLERS = {
    "/track": _track,
    "/untrack": _untrack,
    "/show": _show,
    "/shows": _shows,
    "/movies": _movies,
    "/missing": _missing,
    "/addshow": _addshow,
    "/rmshow": _rmshow,
    "/addmovie": _addmovie,
    "/rmmovie": _rmmovie,
}