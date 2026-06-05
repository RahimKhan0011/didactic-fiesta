import os
import sqlite3
import time
import re
from pathlib import Path
from datetime import datetime, timezone

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

BASE = Path(__file__).parent.parent
DB_MAIN = BASE / "data" / "torrents.db"
DB_HISTORY = BASE / "data" / "history.db"
DB_PATTERNS = BASE / "data" / "patterns.db"

TRACKER_NAMES = {
    "tl": "TorrentLeech",
    "avistaz": "AvistaZ",
    "ar": "AlphaRatio",
    "huno": "HUNO",
    "fl": "FileList",
    "ipt": "IPTorrents",
    "erai": "Erai-raws",
}


def get_db(path):
    conn = sqlite3.connect(str(path), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def trk_name(code):
    return TRACKER_NAMES.get(code or "", code or "?")


def time_ago(ts):
    if not ts:
        return ""
    diff = time.time() - ts
    if diff < 60:
        return f"{int(diff)}s ago"
    if diff < 3600:
        return f"{int(diff / 60)}m ago"
    if diff < 86400:
        return f"{int(diff / 3600)}h ago"
    return f"{int(diff / 86400)}d ago"


def format_size(b):
    if not b:
        return ""
    gb = b / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.1f} GB"
    mb = b / (1024 ** 2)
    if mb >= 1:
        return f"{mb:.0f} MB"
    return f"{int(b / 1024)} KB"


def clean_audio(audio):
    if not audio:
        return ""
    display = {
        "DD 5 1": "DD5.1", "DD 2 0": "DD2.0",
        "DD+ 5 1": "DD+5.1", "DD+ 2 0": "DD+2.0",
        "DDP 5 1": "DDP5.1", "AAC2 0": "AAC2.0",
        "AAC 2 0": "AAC2.0", "DTS-HD.MA": "DTS-HD MA",
    }
    return display.get(audio, audio)


app.jinja_env.globals.update(
    time_ago=time_ago,
    format_size=format_size,
    trk_name=trk_name,
    clean_audio=clean_audio,
)


def tmdb_lookup(name, year=None, is_tv=False):
    api_key = os.getenv("TMDB_API_KEY", "")
    if not api_key or not name:
        return {}
    try:
        import requests as req
        media = "tv" if is_tv else "movie"
        params = {"api_key": api_key, "query": name}
        if year and not is_tv:
            params["year"] = year
        r = req.get(f"https://api.themoviedb.org/3/search/{media}", params=params, timeout=5)
        if r.status_code != 200:
            return {}
        results = r.json().get("results", [])
        if not results:
            return {}
        hit = results[0]
        data = {
            "tmdb_id": hit["id"],
            "rating": hit.get("vote_average", 0),
            "poster": f"https://image.tmdb.org/t/p/w200{hit['poster_path']}" if hit.get("poster_path") else "",
        }
        ext = req.get(
            f"https://api.themoviedb.org/3/{media}/{hit['id']}/external_ids",
            params={"api_key": api_key}, timeout=5
        ).json()
        data["imdb_id"] = ext.get("imdb_id", "")
        return data
    except Exception:
        return {}


@app.route("/")
def dashboard():
    conn = get_db(DB_MAIN)

    total = conn.execute("SELECT COUNT(*) as c FROM torrents").fetchone()["c"]
    today = conn.execute(
        "SELECT COUNT(*) as c FROM torrents WHERE first_seen > ?",
        (time.time() - 86400,)
    ).fetchone()["c"]
    notified = conn.execute(
        "SELECT COUNT(*) as c FROM torrents WHERE notified=1"
    ).fetchone()["c"]
    shows_count = conn.execute(
        "SELECT COUNT(*) as c FROM show_tracker WHERE active=1"
    ).fetchone()["c"]

    recent = conn.execute(
        "SELECT * FROM torrents ORDER BY first_seen DESC LIMIT 25"
    ).fetchall()

    top_groups = conn.execute("""
        SELECT parsed_group, COUNT(*) as cnt
        FROM torrents
        WHERE parsed_group IS NOT NULL AND parsed_group != ''
        GROUP BY parsed_group ORDER BY cnt DESC LIMIT 10
    """).fetchall()

    trackers = conn.execute("""
        SELECT tracker, COUNT(*) as cnt
        FROM torrents GROUP BY tracker ORDER BY cnt DESC
    """).fetchall()

    categories = conn.execute("""
        SELECT category, COUNT(*) as cnt
        FROM torrents
        WHERE category IS NOT NULL AND category != ''
          AND LENGTH(category) < 30
        GROUP BY category ORDER BY cnt DESC LIMIT 15
    """).fetchall()

    families = conn.execute("""
        SELECT family_key, COUNT(*) as cnt, MAX(first_seen) as latest
        FROM torrents
        WHERE family_key IS NOT NULL AND family_key != ''
        GROUP BY family_key
        HAVING cnt > 1
        ORDER BY latest DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    return render_template("dashboard.html",
        total=total, today=today, notified=notified,
        shows_count=shows_count, recent=recent,
        top_groups=top_groups, trackers=trackers,
        categories=categories, families=families
    )


@app.route("/torrents")
def torrents():
    conn = get_db(DB_MAIN)

    page = int(request.args.get("page", 1))
    per_page = 50
    offset = (page - 1) * per_page

    tracker = request.args.get("tracker", "")
    category = request.args.get("category", "")
    group = request.args.get("group", "")
    search = request.args.get("q", "")
    notified_only = request.args.get("notified", "")
    content_type = request.args.get("type", "")
    source = request.args.get("source", "")

    query = "SELECT * FROM torrents WHERE 1=1"
    count_query = "SELECT COUNT(*) as c FROM torrents WHERE 1=1"
    params = []

    if tracker:
        query += " AND tracker=?"
        count_query += " AND tracker=?"
        params.append(tracker)
    if category:
        query += " AND category LIKE ?"
        count_query += " AND category LIKE ?"
        params.append(f"%{category}%")
    if group:
        query += " AND parsed_group=?"
        count_query += " AND parsed_group=?"
        params.append(group)
    if search:
        query += " AND (title LIKE ? OR parsed_name LIKE ?)"
        count_query += " AND (title LIKE ? OR parsed_name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    if notified_only:
        query += " AND notified=1"
        count_query += " AND notified=1"
    if content_type:
        query += " AND content_type=?"
        count_query += " AND content_type=?"
        params.append(content_type)
    if source:
        query += " AND (parsed_source_family=? OR parsed_source=?)"
        count_query += " AND (parsed_source_family=? OR parsed_source=?)"
        params.extend([source, source])

    total = conn.execute(count_query, params).fetchone()["c"]

    query += " ORDER BY pub_timestamp DESC LIMIT ? OFFSET ?"
    rows = conn.execute(query, params + [per_page, offset]).fetchall()

    trackers_list = conn.execute(
        "SELECT DISTINCT tracker FROM torrents WHERE tracker IS NOT NULL ORDER BY tracker"
    ).fetchall()

    categories_list = conn.execute("""
        SELECT category, COUNT(*) as cnt
        FROM torrents
        WHERE category IS NOT NULL AND category != ''
          AND LENGTH(category) < 30
          AND category NOT LIKE '%tt%'
          AND category NOT LIKE '%,%,%,%'
        GROUP BY category HAVING cnt >= 2
        ORDER BY cnt DESC LIMIT 30
    """).fetchall()

    groups_list = conn.execute(
        "SELECT DISTINCT parsed_group FROM torrents WHERE parsed_group IS NOT NULL AND parsed_group != '' ORDER BY parsed_group"
    ).fetchall()

    types_list = conn.execute(
        "SELECT DISTINCT content_type FROM torrents WHERE content_type IS NOT NULL ORDER BY content_type"
    ).fetchall()

    sources_list = conn.execute("""
        SELECT COALESCE(parsed_source_family, parsed_source) as src, COUNT(*) as cnt
        FROM torrents
        WHERE src IS NOT NULL AND src != ''
        GROUP BY src ORDER BY cnt DESC
    """).fetchall()

    conn.close()

    pages = (total + per_page - 1) // per_page

    return render_template("torrents.html",
        rows=rows, page=page, pages=pages, total=total,
        tracker=tracker, category=category, group=group,
        search=search, notified_only=notified_only,
        content_type=content_type, source=source,
        trackers_list=trackers_list,
        categories_list=categories_list,
        groups_list=groups_list,
        types_list=types_list,
        sources_list=sources_list,
    )


@app.route("/torrent/<int:tid>")
def torrent_detail(tid):
    conn = get_db(DB_MAIN)
    row = conn.execute("SELECT * FROM torrents WHERE torrent_id=?", (tid,)).fetchone()
    if not row:
        conn.close()
        return "Not found", 404

    snapshots = conn.execute(
        "SELECT * FROM seeder_snapshots WHERE torrent_id=? ORDER BY checked_at DESC LIMIT 20",
        (tid,)
    ).fetchall()

    family_members = []
    if row["family_key"]:
        family_members = conn.execute(
            """SELECT torrent_id, title, tracker, parsed_group, parsed_source_family,
                      parsed_service_code, parsed_audio, parsed_hdr, seeders, leechers, first_seen
               FROM torrents WHERE family_key=? AND torrent_id!=?
               ORDER BY first_seen ASC""",
            (row["family_key"], tid)
        ).fetchall()

    conn.close()

    extra = {}
    if not row["tmdb_id"] and row["parsed_name"]:
        is_tv = row["content_type"] in ("episode", "season_pack", "complete", "anime_episode")
        if row["imdb_id"]:
            import requests as req
            api_key = os.getenv("TMDB_API_KEY", "")
            if api_key:
                try:
                    r = req.get(
                        f"https://api.themoviedb.org/3/find/{row['imdb_id']}",
                        params={"api_key": api_key, "external_source": "imdb_id"},
                        timeout=5
                    )
                    if r.status_code == 200:
                        results = r.json().get("movie_results", []) + r.json().get("tv_results", [])
                        if results:
                            hit = results[0]
                            extra = {
                                "tmdb_id": hit["id"],
                                "rating": hit.get("vote_average", 0),
                                "poster": f"https://image.tmdb.org/t/p/w200{hit['poster_path']}" if hit.get("poster_path") else "",
                                "imdb_id": row["imdb_id"],
                            }
                except Exception:
                    pass
        if not extra:
            extra = tmdb_lookup(row["parsed_name"], row["parsed_year"], is_tv)

    notifications = []
    try:
        hconn = get_db(DB_HISTORY)
        notifications = hconn.execute(
            "SELECT * FROM notifications WHERE torrent_id=? ORDER BY sent_at DESC",
            (tid,)
        ).fetchall()
        hconn.close()
    except Exception:
        pass

    return render_template("torrent_detail.html",
        t=row, snapshots=snapshots, notifications=notifications,
        extra=extra, family_members=family_members
    )


@app.route("/family/<path:fkey>")
def family_view(fkey):
    conn = get_db(DB_MAIN)

    members = conn.execute(
        """SELECT * FROM torrents WHERE family_key=? ORDER BY first_seen ASC""",
        (fkey,)
    ).fetchall()

    conn.close()

    if not members:
        return "Family not found", 404

    by_variant = {}
    for m in members:
        vk = m["variant_key"] or "unknown"
        if vk not in by_variant:
            by_variant[vk] = {
                "source": m["parsed_source_family"] or m["parsed_source"] or "?",
                "service": m["parsed_service_code"] or "",
                "entries": [],
            }
        by_variant[vk]["entries"].append(m)

    first = members[0]

    return render_template("family.html",
        fkey=fkey, members=members, by_variant=by_variant, first=first
    )


@app.route("/shows")
def shows():
    conn = get_db(DB_MAIN)
    tracked = conn.execute(
        "SELECT * FROM show_tracker WHERE active=1 ORDER BY show_name"
    ).fetchall()

    show_data = []
    for s in tracked:
        episodes = conn.execute("""
            SELECT season, episode, group_name, resolution, found_at
            FROM show_episodes WHERE show_name=?
            ORDER BY season, episode
        """, (s["show_name"],)).fetchall()

        seasons = {}
        for ep in episodes:
            seasons.setdefault(ep["season"], []).append(ep)

        show_data.append({
            "name": s["show_name"],
            "tmdb_id": s["tmdb_id"],
            "latest_s": s["latest_season"],
            "latest_e": s["latest_episode"],
            "seasons": seasons,
            "total_eps": len(episodes),
        })

    conn.close()
    return render_template("shows.html", shows=show_data)


@app.route("/show/<name>")
def show_detail(name):
    conn = get_db(DB_MAIN)

    show = conn.execute(
        "SELECT * FROM show_tracker WHERE show_name=? COLLATE NOCASE", (name,)
    ).fetchone()

    episodes = conn.execute("""
        SELECT * FROM show_episodes WHERE show_name=? COLLATE NOCASE
        ORDER BY season, episode
    """, (name,)).fetchall()

    related = conn.execute("""
        SELECT * FROM torrents WHERE parsed_name LIKE ?
        ORDER BY pub_timestamp DESC LIMIT 50
    """, (f"%{name}%",)).fetchall()

    conn.close()

    seasons = {}
    for ep in episodes:
        seasons.setdefault(ep["season"], []).append(ep)

    missing = {}
    for s, eps in seasons.items():
        ep_nums = sorted(set(e["episode"] for e in eps))
        if ep_nums:
            full = range(ep_nums[0], ep_nums[-1] + 1)
            miss = [e for e in full if e not in ep_nums]
            if miss:
                missing[s] = miss

    return render_template("show_detail.html",
        show=show, name=name, seasons=seasons,
        missing=missing, related=related
    )


@app.route("/movies")
def movies_page():
    conn = get_db(DB_MAIN)
    rows = conn.execute("""
        SELECT * FROM torrents WHERE content_type='movie'
        ORDER BY pub_timestamp DESC LIMIT 100
    """).fetchall()
    conn.close()
    return render_template("movies.html", rows=rows)


@app.route("/games")
def games_page():
    conn = get_db(DB_MAIN)

    page = int(request.args.get("page", 1))
    per_page = 50
    offset = (page - 1) * per_page

    tracker = request.args.get("tracker", "")
    search = request.args.get("q", "")

    query = "SELECT * FROM torrents WHERE content_type IN ('game', 'game_update')"
    count_query = "SELECT COUNT(*) as c FROM torrents WHERE content_type IN ('game', 'game_update')"
    params = []

    if tracker:
        query += " AND tracker=?"
        count_query += " AND tracker=?"
        params.append(tracker)
    if search:
        query += " AND title LIKE ?"
        count_query += " AND title LIKE ?"
        params.append(f"%{search}%")

    total = conn.execute(count_query, params).fetchone()["c"]
    query += " ORDER BY pub_timestamp DESC LIMIT ? OFFSET ?"
    rows = conn.execute(query, params + [per_page, offset]).fetchall()
    conn.close()

    pages = (total + per_page - 1) // per_page

    return render_template("games.html",
        rows=rows, page=page, pages=pages, total=total,
        tracker=tracker, search=search
    )


@app.route("/groups")
def groups():
    conn = get_db(DB_MAIN)

    rows = conn.execute("""
        SELECT parsed_group,
               COUNT(*) as cnt,
               MAX(pub_timestamp) as last_seen,
               MIN(pub_timestamp) as first_seen
        FROM torrents
        WHERE parsed_group IS NOT NULL AND parsed_group != ''
        GROUP BY parsed_group ORDER BY cnt DESC
    """).fetchall()

    conn.close()

    patterns = []
    try:
        pconn = get_db(DB_PATTERNS)
        patterns = pconn.execute("SELECT * FROM group_patterns ORDER BY total_seen DESC").fetchall()
        pconn.close()
    except Exception:
        pass

    pattern_map = {p["group_name"]: p for p in patterns}

    return render_template("groups.html", rows=rows, pattern_map=pattern_map)


@app.route("/stats")
def stats():
    conn = get_db(DB_MAIN)

    by_day = conn.execute("""
        SELECT date(first_seen, 'unixepoch') as day, COUNT(*) as cnt
        FROM torrents GROUP BY day ORDER BY day DESC LIMIT 30
    """).fetchall()

    by_tracker = conn.execute("""
        SELECT tracker, COUNT(*) as cnt
        FROM torrents GROUP BY tracker ORDER BY cnt DESC
    """).fetchall()

    by_category = conn.execute("""
        SELECT category, COUNT(*) as cnt
        FROM torrents
        WHERE category IS NOT NULL AND category != '' AND LENGTH(category) < 30
        GROUP BY category ORDER BY cnt DESC LIMIT 15
    """).fetchall()

    by_type = conn.execute("""
        SELECT content_type, COUNT(*) as cnt
        FROM torrents WHERE content_type IS NOT NULL
        GROUP BY content_type ORDER BY cnt DESC
    """).fetchall()

    by_resolution = conn.execute("""
        SELECT parsed_res, COUNT(*) as cnt
        FROM torrents WHERE parsed_res IS NOT NULL AND parsed_res != ''
        GROUP BY parsed_res ORDER BY cnt DESC
    """).fetchall()

    by_source = conn.execute("""
        SELECT COALESCE(parsed_source_family, parsed_source, '?') as src, COUNT(*) as cnt
        FROM torrents WHERE src != '?'
        GROUP BY src ORDER BY cnt DESC
    """).fetchall()

    hourly = conn.execute("""
        SELECT CAST(strftime('%H', pub_timestamp, 'unixepoch') AS INTEGER) as hour,
               COUNT(*) as cnt
        FROM torrents WHERE pub_timestamp > 0
        GROUP BY hour ORDER BY hour
    """).fetchall()

    conn.close()

    return render_template("stats.html",
        by_day=by_day, by_tracker=by_tracker,
        by_category=by_category, by_type=by_type,
        by_resolution=by_resolution, by_source=by_source,
        hourly=hourly
    )


@app.route("/api/torrents")
def api_torrents():
    conn = get_db(DB_MAIN)
    search = request.args.get("q", "")
    limit = int(request.args.get("limit", 50))

    if search:
        rows = conn.execute(
            "SELECT * FROM torrents WHERE title LIKE ? ORDER BY pub_timestamp DESC LIMIT ?",
            (f"%{search}%", limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM torrents ORDER BY pub_timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()

    conn.close()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)