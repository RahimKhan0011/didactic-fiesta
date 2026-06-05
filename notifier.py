import time
import logging
import sqlite3
import requests

import config
import db
import velocity as vel_mod
import tmdb as tmdb_mod
from models import MatchResult, ContentType, ProfileMode, ParsedRelease, TorrentEntry

log = logging.getLogger("notifier")

API = "https://api.telegram.org/bot{token}/{method}"

TRACKER_NAMES = {
    "tl": "TorrentLeech",
    "avistaz": "AvistaZ",
    "ar": "AlphaRatio",
    "huno": "HUNO",
    "fl": "FileList",
    "ipt": "IPTorrents",
    "erai": "Erai-raws",
}

AUDIO_DISPLAY = {
    "DD 5 1": "DD5.1",
    "DD 2 0": "DD2.0",
    "DD+ 5 1": "DD+5.1",
    "DD+ 2 0": "DD+2.0",
    "DD+ 5.1": "DD+5.1",
    "DD+ 2.0": "DD+2.0",
    "DDP 5 1": "DDP5.1",
    "DDP5.1": "DDP5.1",
    "DDP2.0": "DDP2.0",
    "DDP": "DDP",
    "AAC2 0": "AAC2.0",
    "AAC 2 0": "AAC2.0",
    "DTS-HD.MA": "DTS-HD MA",
}


def _trk_name(code: str) -> str:
    return TRACKER_NAMES.get(code or "", code or "?")


def _clean_audio(audio: str) -> str:
    if not audio:
        return ""
    if audio in AUDIO_DISPLAY:
        return AUDIO_DISPLAY[audio]
    return audio


def send_match(result: MatchResult, episode_info=None, pack_info=None):
    prof = _find_profile(result.profile_name)
    use_tmdb = True
    if prof is not None:
        use_tmdb = prof.get("tmdb", True)

    if use_tmdb and result.entry.parsed:
        p = result.entry.parsed
        is_tv = p.content_type in (
            ContentType.EPISODE,
            ContentType.SEASON_PACK,
            ContentType.COMPLETE,
            ContentType.ANIME_EP,
        )

        tmdb_data = None
        if result.entry.imdb_id:
            tmdb_data = tmdb_mod.lookup_by_imdb(result.entry.imdb_id)
        if not tmdb_data:
            tmdb_data = tmdb_mod.lookup(p.clean_name, p.year, is_tv)

        if tmdb_data:
            result.tmdb_id = tmdb_data.get("tmdb_id", 0)
            result.imdb_id = tmdb_data.get("imdb_id", "") or result.entry.imdb_id or ""
            result.poster_url = tmdb_data.get("poster", "")
            result.tmdb_rating = tmdb_data.get("rating", 0)
            result.tmdb_overview = tmdb_data.get("overview", "")
            db.update_torrent_tmdb(
                result.entry.torrent_id,
                result.tmdb_id,
                result.imdb_id,
                result.poster_url,
            )

    v, v_label = vel_mod.compute_velocity(result.entry.torrent_id, result.entry.seeders)
    result.velocity = v
    result.velocity_label = v_label

    variants = _build_variant_list(result)
    result.variants = variants

    buttons = _build_buttons(result)
    caption = _format_message(result, episode_info, pack_info, caption_mode=True)
    full_text = _format_message(result, episode_info, pack_info, caption_mode=False)

    for chat_id in config.CHAT_IDS:
        msg_id = 0

        if result.poster_url:
            msg_id = _send_photo(chat_id, result.poster_url, caption, buttons)
            if not msg_id:
                msg_id = _send_text(chat_id, full_text, buttons)
        else:
            msg_id = _send_text(chat_id, full_text, buttons)

        if msg_id:
            db.log_notification(result.entry.torrent_id, result.profile_name, chat_id, msg_id)

        show_kw = [k for k in result.matched_keywords if str(k).startswith("show:")]
        movie_kw = [k for k in result.matched_keywords if str(k).startswith("movie:")]
        if (show_kw or movie_kw) and msg_id:
            _pin_message(chat_id, msg_id)

    db.mark_notified(result.entry.torrent_id, result.profile_name)


def send_raw(text: str, buttons=None):
    for chat_id in config.CHAT_IDS:
        _send_text(chat_id, text, buttons)


def delete_message(chat_id: str, message_id: int) -> bool:
    url = API.format(token=config.BOT_TOKEN, method="deleteMessage")
    try:
        r = requests.post(
            url, json={"chat_id": chat_id, "message_id": message_id}, timeout=10
        )
        return r.status_code == 200
    except Exception:
        return False


def _format_message(result: MatchResult, ep_info=None, pack_info=None, caption_mode: bool = False) -> str:
    e = result.entry
    p = e.parsed
    lines = []

    profile_names = [x.strip() for x in str(result.profile_name).split(" + ") if x.strip()]

    if result.is_new_family:
        if result.profile_mode == ProfileMode.RACE:
            tier_emoji = {"tier1": "🥇", "tier2": "🥈", "tier3": "🥉"}.get(result.group_tier.value, "")
            tier_label = result.group_tier.value.upper() if result.group_tier.value.startswith("tier") else ""
            if tier_label:
                lines.append(f"🏁 <b>RACE</b> {tier_emoji}{tier_label}")
            else:
                lines.append("🏁 <b>RACE</b>")
        else:
            lines.append(f"📺 <b>{profile_names[0] if profile_names else result.profile_name}</b>")
    elif result.is_cross_tracker:
        lines.append("🔄 <b>Cross-tracker update</b>")
        lines.append(f"📎 {e.title}")
    else:
        lines.append("🆕 <b>New variant</b>")
        lines.append(f"📎 {e.title}")

    if len(profile_names) > 1:
        lines.append(f"📎 Also: {', '.join(profile_names[1:])}")

    if p and p.is_internal:
        lines.append("🏠 <b>INTERNAL</b>")

    family_title = _build_family_title(p, e)
    lines.append(f"📦 <b>{family_title}</b>")

    if result.tmdb_rating:
        rating_str = f"⭐ {result.tmdb_rating}/10"
        next_ep_str = _get_next_ep_compact(result, p)
        if next_ep_str:
            lines.append(f"{rating_str} | {next_ep_str}")
        else:
            lines.append(rating_str)
    else:
        next_ep_str = _get_next_ep_compact(result, p)
        if next_ep_str:
            lines.append(next_ep_str)

    if result.tmdb_overview:
        limit = 150 if caption_mode else 300
        lines.append(f"📝 {_trim_to_sentence(result.tmdb_overview, limit)}")

    lines.append("")
    lines.append(_format_current_variant(e, p))

    if result.variants:
        lines.append("")
        variant_lines = _format_other_variants(result.variants, caption_mode)
        lines.extend(variant_lines)

    if ep_info:
        ep_lines = _format_episode_info(ep_info)
        if ep_lines:
            lines.append("")
            lines.extend(ep_lines)

    if pack_info:
        pack_lines = _format_season_pack_info(pack_info)
        if pack_lines:
            lines.append("")
            lines.extend(pack_lines)

    show_kw = [k for k in result.matched_keywords if str(k).startswith("show:")]
    movie_kw = [k for k in result.matched_keywords if str(k).startswith("movie:")]

    if show_kw:
        lines.append(f"📋 Watchlist: {show_kw[0].replace('show:', '')}")
    if movie_kw:
        lines.append(f"🎬 Watchlist: {movie_kw[0].replace('movie:', '')}")

    for kw in result.matched_keywords:
        kw = str(kw)
        if kw.startswith("new_show:"):
            lines.append("🌟 Brand new show!")
        elif kw.startswith("premiere:"):
            lines.append("🎬 Season Premiere!")
        elif kw.startswith("season_pack:"):
            lines.append(f"📦 Season Pack: {kw.replace('season_pack:', '')}")
        elif kw.startswith("batch:"):
            lines.append(f"📦 {kw.replace('batch:', '')}")
    text = "\n".join(lines)

    if caption_mode and len(text) > 1024:
        text = text[:1020].rsplit("\n", 1)[0] + "..."
    if not caption_mode and len(text) > 4096:
        text = text[:4090].rsplit("\n", 1)[0] + "..."

    return text


def _build_family_title(p: ParsedRelease, e: TorrentEntry) -> str:
    if not p:
        return e.title

    name = p.clean_name or ""
    parts = [name]

    if p.content_type == ContentType.MOVIE and p.year:
        parts.append(f"({p.year})")
    elif p.season is not None:
        s = f"S{p.season:02d}"
        if p.episode is not None:
            s += f"E{p.episode:02d}"
        parts.append(s)
    elif p.date_key:
        parts.append(p.date_key)

    return " ".join(parts)


def _format_current_variant(e: TorrentEntry, p: ParsedRelease) -> str:
    if not p:
        return f"🆕 {e.title}\n{_trk_name(e.tracker)} <code>/get {e.torrent_id}</code>"

    parts = []

    if p.resolution:
        parts.append(p.resolution)

    src = p.source_family or p.source or ""
    svc = p.service_code or ""
    if src and svc:
        parts.append(f"{src} / {svc}")
    elif src:
        parts.append(src)

    extras = []
    if p.hdr and p.hdr.lower() != "sdr":
        extras.append(p.hdr)
    if p.audio:
        extras.append(_clean_audio(p.audio))
    if extras:
        parts.append(" — ".join(extras))

    parts.append(p.group or "?")

    if e.size_bytes and e.size_bytes > 0:
        gb = e.size_bytes / (1024 ** 3)
        if gb >= 1:
            parts.append(f"💾{gb:.1f}GB")
        else:
            mb = e.size_bytes / (1024 ** 2)
            parts.append(f"💾{mb:.0f}MB")

    if e.seeders or e.leechers:
        parts.append(f"S:{e.seeders} L:{e.leechers}")

    if e.pub_timestamp:
        age = time.time() - e.pub_timestamp
        if age < 60:
            parts.append(f"⚡{int(age)}s")
        elif age < 3600:
            parts.append(f"⏱{int(age / 60)}m")
        else:
            parts.append(f"🕐{int(age / 3600)}h")

    variant_line = "🆕 " + " — ".join(parts)
    tracker_line = f"{_trk_name(e.tracker)} <code>/get {e.torrent_id}</code>"

    return f"{variant_line}\n{tracker_line}"

def _build_variant_list(result: MatchResult) -> list[dict]:
    if not result.dupe_entries:
        return []

    current_id = result.entry.torrent_id
    seen_ids = set()
    seen_ids.add(current_id)

    variants = []
    try:
        conn = sqlite3.connect(str(config.DB_MAIN))
        conn.row_factory = sqlite3.Row

        unique_dupes = list(dict.fromkeys(result.dupe_entries))

        for tid in unique_dupes[:20]:
            if tid in seen_ids:
                continue
            seen_ids.add(tid)

            row = conn.execute(
                """
                SELECT torrent_id, title, tracker, parsed_group, parsed_res,
                       parsed_source, parsed_source_family, parsed_service_code,
                       parsed_codec, parsed_audio, parsed_hdr,
                       seeders, leechers, variant_key
                FROM torrents WHERE torrent_id=?
                """,
                (tid,),
            ).fetchone()
            if row:
                variants.append(dict(row))

        conn.close()
    except Exception:
        pass

    return variants


def _format_other_variants(variants: list[dict], caption_mode: bool) -> list[str]:
    if not variants:
        return []

    by_res = {}
    seen_tids = set()

    for v in variants:
        tid = v.get("torrent_id", 0)
        if tid in seen_tids:
            continue
        seen_tids.add(tid)

        res = v.get("parsed_res") or "?"
        if res not in by_res:
            by_res[res] = {}

        src = v.get("parsed_source_family") or v.get("parsed_source") or ""
        svc = v.get("parsed_service_code") or ""
        grp = v.get("parsed_group") or "?"
        vk = f"{src}|{svc}|{grp}"

        if vk not in by_res[res]:
            by_res[res][vk] = {
                "source_family": src,
                "service": svc,
                "group": grp,
                "audio": v.get("parsed_audio") or "",
                "hdr": v.get("parsed_hdr") or "",
                "entries": [],
            }

        by_res[res][vk]["entries"].append(v)

    lines = []
    max_variants = 4 if caption_mode else 15

    variant_count = 0
    for res in sorted(by_res.keys(), reverse=True):
        res_variants = by_res[res]

        if len(by_res) > 1:
            lines.append(f"📐 {res}:")

        for vk, data in res_variants.items():
            if variant_count >= max_variants:
                remaining = sum(len(d) for r in by_res.values() for d in r.values()) - variant_count
                if remaining > 0:
                    lines.append(f"...+{remaining} more")
                return lines

            variant_count += 1

            src = data["source_family"] or "WEB"
            svc = data["service"]
            header = f"📚 {src}"
            if svc:
                header += f" / {svc}"

            extras = []
            hdr = data["hdr"]
            audio = _clean_audio(data["audio"])
            if hdr and hdr.lower() != "sdr":
                extras.append(hdr)
            if audio:
                extras.append(audio)

            grp = data["group"]
            if extras:
                header += f" — {' — '.join(extras)} — {grp}"
            else:
                header += f" — {grp}"

            lines.append(header)

            tracker_seen = set()
            for entry in data["entries"]:
                tid = entry.get("torrent_id", 0)
                trk = entry.get("tracker", "")
                dedupe_key = f"{trk}_{tid}"
                if dedupe_key in tracker_seen:
                    continue
                tracker_seen.add(dedupe_key)
                lines.append(f"{_trk_name(trk)} <code>/get {tid}</code>")

    return lines

def _format_episode_info(ep_info: dict) -> list[str]:
    lines = []

    if ep_info.get("is_new_episode"):
        prev_s = ep_info.get("prev_latest_s", 0)
        prev_e = ep_info.get("prev_latest_e", 0)
        lines.append(f"🆕 New: S{ep_info['season']:02d}E{ep_info['episode']:02d}")
        if prev_e:
            lines.append(f"📺 Prev: S{prev_s:02d}E{prev_e:02d}")

    if ep_info.get("missing"):
        miss = ", ".join(f"E{m:02d}" for m in ep_info["missing"])
        lines.append(f"❌ Missing S{ep_info['season']:02d}: {miss}")

    return lines


def _format_season_pack_info(pack_info: dict) -> list[str]:
    lines = []

    if pack_info.get("season") is not None:
        season = pack_info["season"]
        lines.append(f"🆕 Season: S{season:02d}")
        
        if pack_info.get("had_previous"):
            prev_s = pack_info.get("prev_latest_s", 0)
            if prev_s and prev_s < season:
                lines.append(f"📺 Prev: S{prev_s:02d}")
        
        deleted = pack_info.get("deleted_count", 0)
        if deleted > 0:
            lines.append(f"🗑️ Removed {deleted} older season pack(s)")

    return lines
    return lines


def _get_next_ep_compact(result: MatchResult, p: ParsedRelease) -> str:
    if not result.tmdb_id or not p:
        return ""

    show_kw = [k for k in result.matched_keywords if str(k).startswith("show:")]
    if not show_kw and not result.is_new_family:
        return ""

    if p.content_type not in (ContentType.EPISODE, ContentType.SEASON_PACK, ContentType.ANIME_EP):
        return ""

    next_ep = tmdb_mod.get_next_episode(result.tmdb_id)
    if not next_ep:
        return ""

    current_s = p.season or 0
    current_e = p.episode or 0

    if next_ep.get("next_air_date"):
        next_s = next_ep.get("next_season", 0)
        next_e = next_ep.get("next_episode", 0)

        is_future = (next_s > current_s) or (next_s == current_s and next_e > current_e)

        if is_future:
            from datetime import datetime
            try:
                air = datetime.strptime(next_ep["next_air_date"], "%Y-%m-%d")
                now = datetime.now()
                diff = (air - now).days
                ep_label = f"S{next_s:02d}E{next_e:02d}"

                if next_e > current_e + 1 or next_s > current_s:
                    latest_str = f"Latest: {ep_label}"
                else:
                    latest_str = ""

                if diff < 0:
                    if latest_str:
                        return f"📅 {ep_label} already aired | This is E{current_e:02d}"
                    return f"📅 {ep_label} already aired"
                elif diff == 0:
                    return f"📅 {ep_label} airs TODAY"
                elif diff == 1:
                    return f"📅 {ep_label} airs TOMORROW"
                elif diff <= 14:
                    return f"📅 {ep_label} in {diff}d"
                else:
                    return f"📅 {ep_label} on {next_ep['next_air_date']}"
            except Exception:
                return ""

    if next_ep.get("status") in ("Ended", "Canceled"):
        return f"📺 {next_ep['status']}"

    return ""

def _trim_to_sentence(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    if len(text) <= max_len:
        return text

    cut = text[:max_len]

    candidates = []
    for marker in [". ", "! ", "? "]:
        idx = cut.rfind(marker)
        if idx > 40:
            candidates.append(idx + 1)

    if candidates:
        return cut[:max(candidates)].strip()

    dot = cut.rfind(".")
    excl = cut.rfind("!")
    qmark = cut.rfind("?")
    best = max(dot, excl, qmark)
    if best > 40:
        return cut[:best + 1].strip()

    last_space = cut.rfind(" ")
    if last_space > 40:
        return cut[:last_space].strip() + "..."

    return cut.strip() + "..."


def _build_buttons(result: MatchResult) -> dict:
    buttons = []
    row1 = []

    if result.entry.page_url:
        row1.append({"text": f"📄 {_trk_name(result.entry.tracker)}", "url": result.entry.page_url})
    if result.entry.download_url:
        row1.append({"text": "⬇️ Download", "url": result.entry.download_url})
    if row1:
        buttons.append(row1)

    row2 = []
    if result.imdb_id:
        row2.append({"text": "🎬 IMDb", "url": f"https://www.imdb.com/title/{result.imdb_id}/"})
    if result.tmdb_id:
        media = (
            "tv"
            if result.entry.parsed
            and result.entry.parsed.content_type
            in (ContentType.EPISODE, ContentType.SEASON_PACK, ContentType.COMPLETE)
            else "movie"
        )
        row2.append(
            {"text": "🎬 TMDB", "url": f"https://www.themoviedb.org/{media}/{result.tmdb_id}"}
        )
    if row2:
        buttons.append(row2)

    return {"inline_keyboard": buttons} if buttons else {}


def _pin_message(chat_id: str, message_id: int):
    url = API.format(token=config.BOT_TOKEN, method="pinChatMessage")
    try:
        requests.post(
            url,
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "disable_notification": True,
            },
            timeout=10,
        )
    except Exception:
        pass


def _send_text(chat_id: str, text: str, buttons=None) -> int:
    url = API.format(token=config.BOT_TOKEN, method="sendMessage")
    payload = {
        "chat_id": chat_id,
        "text": text[:4096],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if buttons:
        payload["reply_markup"] = buttons
    return _do_send(url, payload)


def _send_photo(chat_id: str, photo_url: str, caption: str, buttons=None) -> int:
    url = API.format(token=config.BOT_TOKEN, method="sendPhoto")
    payload = {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption[:1024],
        "parse_mode": "HTML",
    }
    if buttons:
        payload["reply_markup"] = buttons
    return _do_send(url, payload)


def _do_send(url: str, payload: dict) -> int:
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 429:
            wait = r.json().get("parameters", {}).get("retry_after", 10)
            log.warning(f"Rate limited, sleeping {wait}s")
            time.sleep(wait)
            return _do_send(url, payload)
        if r.status_code == 200:
            return r.json().get("result", {}).get("message_id", 0)
        log.error(f"TG error {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.error(f"TG send failed: {e}")
    return 0


def _find_profile(desc: str):
    for name, p in config.get_profiles().items():
        if p.get("desc") == desc or name == desc:
            return p
    return None