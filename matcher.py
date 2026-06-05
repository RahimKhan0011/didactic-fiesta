import time
import logging
import sqlite3

from models import (
    TorrentEntry,
    ParsedRelease,
    MatchResult,
    ProfileMode,
    GroupTier,
    ContentType,
)
import config
import db
import rule_engine

log = logging.getLogger("matcher")

BOT_GROUPS = ["megusta"]


def resolve_group_tier(group: str) -> GroupTier:
    if not group:
        return GroupTier.NONE

    group_lower = group.lower()
    groups = config.get_groups()

    banned = [g.lower() for g in groups.get("banned", [])]
    if group_lower in banned:
        return GroupTier.BANNED

    for tier_name in ["tier1", "tier2", "tier3"]:
        tier_groups = [g.lower() for g in groups.get(tier_name, [])]
        if group_lower in tier_groups:
            return GroupTier(tier_name)

    return GroupTier.NONE


def is_tier_alert_enabled(tier: GroupTier) -> bool:
    if tier == GroupTier.NONE:
        return True
    alerts = config.get_tier_alerts()
    return alerts.get(tier.value, True)


def is_ignored_category(category: str) -> bool:
    ignored = config.get_ignore_categories()
    cat_lower = (category or "").lower()
    for ig in ignored:
        if ig.lower() in cat_lower:
            emergency = config.get_emergency_keywords()
            return not any(ek.lower() in cat_lower for ek in emergency)
    return False


def is_megusta_excluded(parsed: ParsedRelease) -> bool:
    if not parsed.group or parsed.group.lower() not in BOT_GROUPS:
        return False

    try:
        from quiet import get_megusta_exclusions
        exclusions = get_megusta_exclusions()
    except Exception:
        return False

    now = time.time()
    for exc in exclusions:
        if exc.get("expires", 0) < now:
            continue

        exc_name = exc.get("name", "").lower()
        exc_season = exc.get("season")
        exc_episode = exc.get("episode")

        if exc_name and exc_name in (parsed.clean_name or "").lower():
            if exc_season is not None and parsed.season != exc_season:
                continue
            if exc_episode is not None and parsed.episode != exc_episode:
                continue
            return True

    return False


def match_entry(entry: TorrentEntry, parsed: ParsedRelease) -> list[MatchResult]:
    results = []
    profiles = config.get_profiles()
    now = time.time()
    age = now - entry.pub_timestamp if entry.pub_timestamp else 0

    tier = resolve_group_tier(parsed.group)

    if tier == GroupTier.BANNED:
        log.debug(f"Banned: {parsed.group} — {entry.title}")
        return []

    if parsed.group and parsed.group.lower() in BOT_GROUPS:
        if db.was_group_episode_notified(
            parsed.clean_name,
            parsed.group,
            parsed.season,
            parsed.episode,
        ):
            log.debug(f"Bot-group repeat skip: {entry.title[:80]}")
            return []

        if is_megusta_excluded(parsed):
            log.debug(f"MeGusta excluded: {entry.title[:80]}")
            return []

    if parsed.content_type in (ContentType.EPISODE, ContentType.ANIME_EP):
        if parsed.season is not None and parsed.episode is not None:
            latest_known = db.latest_episode_for_show_season(parsed.clean_name, parsed.season)
            if latest_known is not None and latest_known > parsed.episode:
                log.debug(
                    f"Older episode skipped: {parsed.clean_name} "
                    f"S{parsed.season:02d}E{parsed.episode:02d} "
                    f"(latest known E{latest_known:02d})"
                )
                return "__OLDER_SKIPPED__"

    title_lower = (entry.title or "").lower()
    if parsed.content_type in (ContentType.EPISODE, ContentType.ANIME_EP):
        if parsed.season is not None and parsed.episode is not None:
            if db.season_pack_exists(parsed.clean_name, parsed.season, parsed.resolution):
                log.debug(f"Season pack exists, skip episode: {entry.title[:80]}")
                return []
    for prof_name, prof in profiles.items():
        mode = ProfileMode(prof.get("mode", "content"))

        if mode == ProfileMode.RACE:
            max_age = prof.get("max_age", 60) * 60
            if age > max_age and entry.pub_timestamp > 0:
                continue

        exclude_refs = [e.strip() for e in str(prof.get("exclude", "")).split(",") if e.strip()]
        defs = config.get_definitions()

        excluded = False
        for ref in exclude_refs:
            if ref in defs:
                for val in defs[ref]:
                    if val.lower() in title_lower:
                        excluded = True
                        break
            elif ref.lower() in title_lower:
                excluded = True
            if excluded:
                break

        if excluded:
            continue

        if is_ignored_category(entry.category):
            emergency = config.get_emergency_keywords()
            if not any(ek.lower() in title_lower for ek in emergency):
                continue

        rule = prof.get("rule", "")
        if not rule:
            continue

        matched, matched_kw = rule_engine.evaluate_rule(rule, entry, parsed, tier)
        if not matched:
            continue

        has_tier_match = any(str(k).startswith("group:") and "tier" in str(k) for k in matched_kw)
        if has_tier_match and not is_tier_alert_enabled(tier):
            continue

        results.append(
            MatchResult(
                entry=entry,
                profile_name=prof.get("desc", prof_name),
                profile_mode=mode,
                group_tier=tier,
                matched_keywords=matched_kw,
                age_seconds=age,
                family_key=parsed.family_key,
            )
        )

    _check_emergency(entry, parsed, results, tier, age)

    if not results:
        return []

    merged = _dedupe_results(results)

    final_results = []
    for result in merged:
        exact_dupes = _get_exact_dupes(parsed.exact_key, entry.torrent_id)
        other_variants = _get_other_variants(parsed.family_key, parsed.variant_key, entry.torrent_id)
        exact_notified = _get_exact_notified(parsed.exact_key, entry.torrent_id)
        family_existed = _family_exists_before(parsed.family_key, entry.torrent_id)

        related_ids = list(dict.fromkeys(
            [x["torrent_id"] for x in exact_dupes + other_variants]
        ))

        result.dupe_entries = related_ids
        result.is_dupe = len(related_ids) > 0
        result.is_new_family = not family_existed
        result.is_new_variant = not _variant_exists_before(parsed.variant_key, entry.torrent_id)
        result.is_cross_tracker = len(exact_dupes) > 0

        if family_existed:
            db.mark_notified(entry.torrent_id, result.profile_name)
            _handle_family_update(entry, parsed, result, related_ids)
            result.is_cross_tracker = bool(exact_notified)
            result.is_new_variant = not bool(exact_notified)
            final_results.append(result)
            log.debug(f"Family update collected: {entry.title[:80]}")
            break

        final_results.append(result)

    return final_results

def _handle_family_update(
    entry: TorrentEntry,
    parsed: ParsedRelease,
    result: MatchResult,
    related_ids: list[int],
):
    result.dupe_entries = related_ids
    result.is_dupe = len(related_ids) > 0
    result.is_new_family = False

def _get_family_notifications(family_key: str) -> list[dict]:
    if not family_key:
        return []

    mconn = sqlite3.connect(str(config.DB_MAIN))
    mconn.row_factory = sqlite3.Row
    hconn = sqlite3.connect(str(config.DB_HISTORY))
    hconn.row_factory = sqlite3.Row

    torrents = mconn.execute(
        """
        SELECT torrent_id FROM torrents
        WHERE family_key = ?
          AND notified = 1
        ORDER BY first_seen ASC
        """,
        (family_key,),
    ).fetchall()

    result = []
    seen_msg_ids = set()
    for t in torrents:
        rows = hconn.execute(
            "SELECT * FROM notifications WHERE torrent_id = ? ORDER BY sent_at DESC",
            (t["torrent_id"],),
        ).fetchall()
        for r in rows:
            mid = r["message_id"]
            if mid and mid not in seen_msg_ids:
                seen_msg_ids.add(mid)
                result.append(dict(r))

    mconn.close()
    hconn.close()
    return result

def _family_exists_before(family_key: str, exclude_id: int) -> bool:
    if not family_key:
        return False

    conn = sqlite3.connect(str(config.DB_MAIN))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT 1 FROM torrents
        WHERE family_key = ?
          AND torrent_id != ?
        LIMIT 1
        """,
        (family_key, exclude_id),
    ).fetchone()
    conn.close()
    return row is not None


def _variant_exists_before(variant_key: str, exclude_id: int) -> bool:
    if not variant_key:
        return False

    conn = sqlite3.connect(str(config.DB_MAIN))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT 1 FROM torrents
        WHERE variant_key = ?
          AND torrent_id != ?
        LIMIT 1
        """,
        (variant_key, exclude_id),
    ).fetchone()
    conn.close()
    return row is not None


def _get_exact_notified(exact_key: str, exclude_id: int) -> list[dict]:
    if not exact_key:
        return []

    conn = sqlite3.connect(str(config.DB_MAIN))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT torrent_id, tracker, parsed_group, first_seen
        FROM torrents
        WHERE exact_key = ?
          AND torrent_id != ?
          AND notified = 1
        ORDER BY first_seen ASC
        """,
        (exact_key, exclude_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_exact_dupes(exact_key: str, exclude_id: int) -> list[dict]:
    if not exact_key:
        return []

    conn = sqlite3.connect(str(config.DB_MAIN))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT torrent_id, tracker, parsed_group, parsed_res, parsed_source,
               parsed_codec, parsed_audio, parsed_hdr, seeders, leechers,
               page_url, download_url, first_seen
        FROM torrents
        WHERE exact_key = ?
          AND torrent_id != ?
        ORDER BY first_seen ASC
        """,
        (exact_key, exclude_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_other_variants(family_key: str, variant_key: str, exclude_id: int) -> list[dict]:
    if not family_key:
        return []

    conn = sqlite3.connect(str(config.DB_MAIN))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT torrent_id, tracker, parsed_group, parsed_res, parsed_source,
               parsed_codec, parsed_audio, parsed_hdr, seeders, leechers,
               page_url, download_url, first_seen, variant_key
        FROM torrents
        WHERE family_key = ?
          AND torrent_id != ?
          AND COALESCE(variant_key, '') != COALESCE(?, '')
        ORDER BY first_seen ASC
        """,
        (family_key, exclude_id, variant_key),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_notification_messages_for_exact(exact_key: str) -> list[dict]:
    if not exact_key:
        return []

    mconn = sqlite3.connect(str(config.DB_MAIN))
    mconn.row_factory = sqlite3.Row
    hconn = sqlite3.connect(str(config.DB_HISTORY))
    hconn.row_factory = sqlite3.Row

    torrents = mconn.execute(
        """
        SELECT torrent_id FROM torrents
        WHERE (exact_key = ? OR exact_key IS NULL)
          AND notified = 1
        """,
        (exact_key,),
    ).fetchall()

    if not torrents:
        parts = exact_key.rsplit("|", 4)
        if len(parts) > 1:
            family_part = parts[0]
            torrents = mconn.execute(
                """
                SELECT torrent_id FROM torrents
                WHERE family_key = ?
                  AND notified = 1
                """,
                (family_part,),
            ).fetchall()

    result = []
    for t in torrents:
        rows = hconn.execute(
            "SELECT * FROM notifications WHERE torrent_id = ? ORDER BY sent_at DESC",
            (t["torrent_id"],),
        ).fetchall()
        for r in rows:
            result.append(dict(r))

    mconn.close()
    hconn.close()
    return result


def _check_emergency(entry, parsed, results, tier, age):
    if results:
        return

    emergency = config.get_emergency_keywords()
    title_lower = (entry.title or "").lower()
    hits = [ek for ek in emergency if ek.lower() in title_lower]

    if hits:
        results.append(
            MatchResult(
                entry=entry,
                profile_name="⚠️ EMERGENCY",
                profile_mode=ProfileMode.RACE,
                group_tier=tier,
                matched_keywords=[f"emergency:{h}" for h in hits],
                age_seconds=age,
                family_key=parsed.family_key,
            )
        )


def _dedupe_results(results: list[MatchResult]) -> list[MatchResult]:
    by_key = {}

    for result in results:
        tracker = result.entry.tracker or "unknown"
        tid = result.entry.torrent_id
        key = f"{tracker}_{tid}"

        if key not in by_key:
            by_key[key] = result
            continue

        existing = by_key[key]

        existing.matched_keywords = list(
            dict.fromkeys(existing.matched_keywords + result.matched_keywords)
        )

        if result.profile_name not in existing.profile_name:
            existing.profile_name = f"{existing.profile_name} + {result.profile_name}"

        if result.group_tier.value.startswith("tier"):
            existing.group_tier = result.group_tier

        if result.profile_mode == ProfileMode.RACE:
            existing.profile_mode = ProfileMode.RACE

    return list(by_key.values())