import time
import sqlite3
import config


def _recent(args: str) -> str:
    hours = 6
    if args and args.strip().isdigit():
        hours = int(args.strip())
    import db
    torrents = db.get_recent_torrents(hours)
    if not torrents:
        return f"No matches in last {hours}h"
    lines = [f"📋 <b>Last {hours}h</b> ({len(torrents)} entries)\n"]
    for t in torrents[:30]:
        title = t["title"][:50]
        group = t["parsed_group"] or "?"
        notif = "✅" if t["notified"] else "⬜"
        lines.append(f"{notif} <code>{group}</code> | {title}")
    if len(torrents) > 30:
        lines.append(f"\n...+{len(torrents)-30} more")
    return "\n".join(lines)


def _search(args: str) -> str:
    if not args:
        return (
            "Usage:\n"
            "/search keyword\n"
            "/search tl keyword\n"
            "/search az keyword"
        )

    tracker_filter = None
    query = args.strip()

    parts = query.split(maxsplit=1)
    if parts[0].lower() in ("tl", "az", "ar", "huno", "fl", "ipt", "erai", "all"):
        if parts[0].lower() == "tl":
            tracker_filter = "tl"
        elif parts[0].lower() == "az":
            tracker_filter = "avistaz"
        elif parts[0].lower() == "ar":
            tracker_filter = "ar"
        elif parts[0].lower() == "huno":
            tracker_filter = "huno"
        elif parts[0].lower() == "fl":
            tracker_filter = "fl"
        elif parts[0].lower() == "ipt":
            tracker_filter = "ipt"
        elif parts[0].lower() == "erai":
            tracker_filter = "erai"
        if len(parts) > 1:
            query = parts[1].strip()
        else:
            return "Usage: /search tl keyword"

    conn = sqlite3.connect(str(config.DB_MAIN))
    conn.row_factory = sqlite3.Row

    if tracker_filter:
        rows = conn.execute("""
            SELECT * FROM torrents
            WHERE tracker = ?
              AND (title LIKE ? OR parsed_name LIKE ? OR parsed_group LIKE ?)
            ORDER BY pub_timestamp DESC LIMIT 20
        """, (tracker_filter, f"%{query}%", f"%{query}%", f"%{query}%")).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM torrents
            WHERE (title LIKE ? OR parsed_name LIKE ? OR parsed_group LIKE ?)
            ORDER BY pub_timestamp DESC LIMIT 20
        """, (f"%{query}%", f"%{query}%", f"%{query}%")).fetchall()

    conn.close()

    if not rows:
        where = tracker_filter or "all"
        return f"No results for: {query} ({where})"

    TRKS = {
        "tl": "TL", "avistaz": "AZ", "ar": "AR",
        "huno": "HUNO", "fl": "FL", "ipt": "IPT", "erai": "Erai",
    }

    lines = [f"🔍 <b>{query}</b> ({len(rows)} results)\n"]

    for r in rows:
        notif = "✅" if r["notified"] else "⬜"
        trk = TRKS.get(r["tracker"] or "", r["tracker"] or "?")
        title = r["title"] or ""
        group = r["parsed_group"] or ""
        res = r["parsed_res"] or ""
        src = r["parsed_source_family"] or r["parsed_source"] or ""
        svc = r["parsed_service_code"] or ""
        audio = r["parsed_audio"] or ""
        seeds = r["seeders"] or 0
        leech = r["leechers"] or 0
        size = ""
        if r["size_bytes"]:
            gb = r["size_bytes"] / (1024 ** 3)
            if gb >= 1:
                size = f"{gb:.1f}GB"
            else:
                size = f"{int(r['size_bytes'] / (1024 ** 2))}MB"

        tech = []
        if src:
            tech.append(src)
        if svc:
            tech.append(svc)
        if res:
            tech.append(res)

        tech_str = " ".join(tech)

        lines.append(f"{notif} [{trk}] {title}")
        lines.append(f"  {group} | {tech_str} | S:{seeds} L:{leech} {size}")
        lines.append(f"  <code>/get {r['torrent_id']}</code>")

    return "\n".join(lines)


def _dupes(args: str) -> str:
    conn = sqlite3.connect(str(config.DB_MAIN))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT parsed_name, parsed_year, parsed_res, COUNT(*) as cnt
        FROM torrents
        WHERE parsed_name IS NOT NULL AND parsed_name != '' AND first_seen > ?
        GROUP BY parsed_name, parsed_year, parsed_res
        HAVING cnt > 1 ORDER BY cnt DESC LIMIT 20
    """, (time.time() - 86400,)).fetchall()
    conn.close()
    if not rows:
        return "No duplicates in last 24h"
    lines = ["⚠️ <b>Duplicates (24h)</b>\n"]
    for r in rows:
        year = f" ({r['parsed_year']})" if r["parsed_year"] else ""
        res = f" [{r['parsed_res']}]" if r["parsed_res"] else ""
        lines.append(f"  {r['parsed_name']}{year}{res} — {r['cnt']} releases")
    return "\n".join(lines)

def _get(args: str):
    if not args or not args.strip().isdigit():
        return "Usage: /get ID"

    tid = int(args.strip())

    import sqlite3
    conn = sqlite3.connect(str(config.DB_MAIN))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM torrents WHERE torrent_id=?", (tid,)).fetchone()

    if not row:
        conn.close()
        return f"Not found: {tid}"

    TRKS = {
        "tl": "TorrentLeech", "avistaz": "AvistaZ", "ar": "AlphaRatio",
        "huno": "HUNO", "fl": "FileList", "ipt": "IPTorrents", "erai": "Erai-raws",
    }

    trk = TRKS.get(row["tracker"] or "", row["tracker"] or "?")
    lines = []

    lines.append(f"📦 <b>{row['title']}</b>")
    lines.append(f"🆔 <code>{tid}</code>")
    lines.append("")

    if row["parsed_name"]:
        lines.append(f"🎬 {row['parsed_name']}")
    if row["parsed_year"]:
        lines.append(f"📅 {row['parsed_year']}")

    info = []
    if row["tracker"]:
        info.append(f"🌐 {trk}")
    if row["category"]:
        info.append(f"📁 {row['category']}")
    if row["parsed_res"]:
        info.append(f"📐 {row['parsed_res']}")
    src = row["parsed_source_family"] or row["parsed_source"]
    if src:
        info.append(f"💿 {src}")
    if row["parsed_service_code"]:
        info.append(f"🏷 {row['parsed_service_code']}")
    if row["parsed_codec"]:
        info.append(f"🔧 {row['parsed_codec']}")
    if row["parsed_audio"]:
        info.append(f"🔊 {row['parsed_audio']}")
    if row["parsed_hdr"] and row["parsed_hdr"].lower() != "sdr":
        info.append(f"🌈 {row['parsed_hdr']}")
    if info:
        lines.append(" | ".join(info))

    if row["parsed_group"]:
        lines.append(f"👤 {row['parsed_group']}")

    if row["size_bytes"] and row["size_bytes"] > 0:
        gb = row["size_bytes"] / (1024 ** 3)
        if gb >= 1:
            lines.append(f"💾 {gb:.1f} GB")
        else:
            lines.append(f"💾 {int(row['size_bytes'] / (1024**2))} MB")

    lines.append(f"👥 S:{row['seeders']} L:{row['leechers']}")

    if row["pub_timestamp"]:
        age = time.time() - row["pub_timestamp"]
        if age < 3600:
            lines.append(f"⏱ {int(age/60)}m ago")
        elif age < 86400:
            lines.append(f"🕐 {int(age/3600)}h ago")
        else:
            lines.append(f"📅 {int(age/86400)}d ago")

    if row["parsed_season"] is not None:
        ep = f"S{row['parsed_season']:02d}"
        if row["parsed_episode"] is not None:
            ep += f"E{row['parsed_episode']:02d}"
        lines.append(f"📺 {ep}")

    if row["notified"]:
        lines.append(f"✅ {row['matched_profile'] or '?'}")

    family_key = row["family_key"]
    if family_key:
        family = conn.execute("""
            SELECT torrent_id, tracker, parsed_group, parsed_res,
                   parsed_source_family, parsed_source, parsed_service_code,
                   parsed_audio, parsed_hdr, seeders, leechers, page_url, download_url
            FROM torrents
            WHERE family_key = ? AND torrent_id != ?
            ORDER BY first_seen ASC
        """, (family_key, tid)).fetchall()

        if family:
            by_res = {}
            for f in family:
                res = f["parsed_res"] or "?"
                if res not in by_res:
                    by_res[res] = []
                by_res[res].append(f)

            lines.append(f"\n📦 Family: {len(family)} other releases")

            for res in sorted(by_res.keys(), reverse=True):
                if len(by_res) > 1:
                    lines.append(f"📐 {res}:")

                seen = set()
                for f in by_res[res]:
                    ftid = f["torrent_id"]
                    if ftid in seen:
                        continue
                    seen.add(ftid)

                    ftrk = TRKS.get(f["tracker"] or "", f["tracker"] or "?")
                    grp = f["parsed_group"] or "?"
                    src = f["parsed_source_family"] or f["parsed_source"] or ""
                    svc = f["parsed_service_code"] or ""
                    aud = f["parsed_audio"] or ""
                    hdr = f["parsed_hdr"] or ""

                    parts = []
                    if src:
                        parts.append(src)
                    if svc:
                        parts.append(svc)
                    if hdr and hdr.lower() != "sdr":
                        parts.append(hdr)
                    if aud:
                        parts.append(aud)
                    parts.append(grp)

                    tech = " — ".join(parts) if parts else grp
                    lines.append(f"  {ftrk} {tech} S:{f['seeders']} L:{f['leechers']} <code>/get {ftid}</code>")

    if row["parsed_name"] and row["parsed_season"] is not None:
        conn3 = sqlite3.connect(str(config.DB_MAIN))
        conn3.row_factory = sqlite3.Row
        eps = conn3.execute("""
            SELECT DISTINCT parsed_episode, parsed_res, parsed_group, tracker, torrent_id
            FROM torrents
            WHERE parsed_name = ? COLLATE NOCASE
              AND parsed_season = ?
              AND parsed_episode IS NOT NULL
              AND torrent_id != ?
            ORDER BY parsed_episode DESC
            LIMIT 20
        """, (row["parsed_name"], row["parsed_season"], tid)).fetchall()
        conn3.close()

        if eps:
            seen_eps = set()
            ep_lines = []
            for ep in eps:
                ep_num = ep["parsed_episode"]
                if ep_num in seen_eps:
                    continue
                seen_eps.add(ep_num)

                etrk = TRKS.get(ep["tracker"] or "", ep["tracker"] or "?")
                ep_lines.append(
                    f"  E{ep_num:02d} [{etrk}] {ep['parsed_group'] or '?'} <code>/get {ep['torrent_id']}</code>"
                )

            if ep_lines:
                lines.append(f"\n📺 S{row['parsed_season']:02d} episodes:")
                lines.extend(ep_lines[:10])
                if len(ep_lines) > 10:
                    lines.append(f"  ...+{len(ep_lines)-10} more")

    conn.close()

    buttons = {"inline_keyboard": []}
    r1 = []
    if row["page_url"]:
        r1.append({"text": f"📄 {trk}", "url": row["page_url"]})
    if row["download_url"]:
        r1.append({"text": "⬇️ Download", "url": row["download_url"]})
    if r1:
        buttons["inline_keyboard"].append(r1)

    r2 = []
    if row["imdb_id"]:
        r2.append({"text": "🎬 IMDb", "url": f"https://imdb.com/title/{row['imdb_id']}"})
    if row["tmdb_id"]:
        media = "tv" if row["content_type"] in ("episode", "season_pack", "complete") else "movie"
        r2.append({"text": "🎬 TMDB", "url": f"https://themoviedb.org/{media}/{row['tmdb_id']}"})
    if r2:
        buttons["inline_keyboard"].append(r2)

    if family_key:
        family_dupes = conn if False else None
        try:
            conn2 = sqlite3.connect(str(config.DB_MAIN))
            conn2.row_factory = sqlite3.Row
            alt_trackers = conn2.execute("""
                SELECT DISTINCT tracker, page_url, download_url
                FROM torrents
                WHERE family_key = ? AND torrent_id != ? AND page_url IS NOT NULL
                LIMIT 4
            """, (family_key, tid)).fetchall()
            conn2.close()

            for alt in alt_trackers:
                atrk = TRKS.get(alt["tracker"] or "", alt["tracker"] or "?")
                ar = []
                if alt["page_url"]:
                    ar.append({"text": f"📄 {atrk}", "url": alt["page_url"]})
                if alt["download_url"]:
                    ar.append({"text": f"⬇️ {atrk}", "url": alt["download_url"]})
                if ar:
                    buttons["inline_keyboard"].append(ar)
        except Exception:
            pass

    text = "\n".join(lines)

    if buttons["inline_keyboard"]:
        return (text, buttons)
    return text

def _find_same_release(row) -> list:
    import sqlite3
    if not row["parsed_name"] or not row["parsed_group"]:
        return []
    conn = sqlite3.connect(str(config.DB_MAIN))
    conn.row_factory = sqlite3.Row

    query = """
        SELECT torrent_id, tracker, seeders, leechers, page_url, download_url
        FROM torrents
        WHERE parsed_name = ? COLLATE NOCASE
          AND parsed_group = ? COLLATE NOCASE
          AND COALESCE(parsed_res, '') = COALESCE(?, '')
          AND torrent_id != ?
    """
    params = [
        row["parsed_name"], row["parsed_group"],
        row["parsed_res"] or '', row["torrent_id"]
    ]

    if row["parsed_season"] is not None:
        query += " AND parsed_season=?"
        params.append(row["parsed_season"])
    if row["parsed_episode"] is not None:
        query += " AND parsed_episode=?"
        params.append(row["parsed_episode"])

    query += " ORDER BY seeders DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

HANDLERS = {
    "/recent": _recent,
    "/search": _search,
    "/dupes": _dupes,
    "/get": _get,
}