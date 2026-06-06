import re
import logging

import config
from models import TorrentEntry, ParsedRelease, GroupTier, ContentType

log = logging.getLogger("rules")


def evaluate_rule(rule: str, entry: TorrentEntry, parsed: ParsedRelease, group_tier: GroupTier) -> tuple[bool, list[str]]:
    matched = []
    try:
        result = _eval_expr(rule.strip(), entry, parsed, group_tier, matched)
        deduped = list(dict.fromkeys(matched))
        return result, deduped
    except Exception as e:
        log.error(f"Rule eval error: {rule} — {e}")
        return False, []


def _eval_expr(expr: str, entry: TorrentEntry, parsed: ParsedRelease, tier: GroupTier, matched: list[str]) -> bool:
    expr = expr.strip()
    if not expr:
        return False

    while _is_wrapped_group(expr):
        expr = expr[1:-1].strip()

    or_parts = _split_top_level(expr, " or ")
    if len(or_parts) > 1:
        return any(_eval_expr(part, entry, parsed, tier, matched) for part in or_parts)

    and_parts = _split_top_level(expr, " and ")
    if len(and_parts) > 1:
        return all(_eval_expr(part, entry, parsed, tier, matched) for part in and_parts)

    return _eval_token(expr, entry, parsed, tier, matched)


def _is_wrapped_group(expr: str) -> bool:
    if not expr.startswith("[") or not expr.endswith("]"):
        return False

    depth = 0
    for i, ch in enumerate(expr):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if depth == 0 and i < len(expr) - 1:
            return False
    return depth == 0


def _split_top_level(expr: str, delimiter: str) -> list[str]:
    parts = []
    depth = 0
    current = []
    i = 0

    while i < len(expr):
        ch = expr[i]

        if ch == "[":
            depth += 1
            current.append(ch)
            i += 1
            continue

        if ch == "]":
            depth -= 1
            current.append(ch)
            i += 1
            continue

        if depth == 0 and expr[i:i + len(delimiter)] == delimiter:
            parts.append("".join(current).strip())
            current = []
            i += len(delimiter)
            continue

        current.append(ch)
        i += 1

    tail = "".join(current).strip()
    if tail:
        parts.append(tail)

    return parts


def _eval_token(expr: str, entry: TorrentEntry, parsed: ParsedRelease, tier: GroupTier, matched: list[str]) -> bool:
    token = expr.strip()
    if token.startswith("[") and token.endswith("]"):
        token = token[1:-1].strip()

    title_lower = (entry.title or "").lower()
    clean_name_lower = (parsed.clean_name or "").lower()
    defs = config.get_definitions()
    groups = config.get_groups()
    watchlists = config.get_watchlists()

    if token == "recent_year":
        from datetime import datetime
        current_year = datetime.now().year
        if parsed.year and parsed.year >= current_year - 1:
            matched.append(f"year:{parsed.year}")
            return True
        return False

    if token == "new_show":
        if parsed.season == 1 and parsed.episode == 1:
            matched.append("new_show:S01E01")
            return True
        return False

    if token == "new_show_early":
        if parsed.season == 1 and parsed.episode is not None and parsed.episode <= 3:
            matched.append(f"new_show:S01E{parsed.episode:02d}")
            return True
        return False

    if token == "season_premiere":
        if parsed.season is not None and parsed.episode == 1:
            matched.append(f"premiere:S{parsed.season:02d}E01")
            return True
        return False

    if token == "season_pack":
        if parsed.content_type in (ContentType.EPISODE, ContentType.ANIME_EP):
            return False

        if parsed.content_type == ContentType.SEASON_PACK:
            season_str = f"S{parsed.season:02d}" if parsed.season is not None else "full"
            matched.append(f"season_pack:{season_str}")
            return True

        if parsed.content_type == ContentType.COMPLETE:
            matched.append("season_pack:complete")
            return True

        if parsed.season is not None and parsed.episode is None:
            matched.append(f"season_pack:S{parsed.season:02d}")
            return True

        title_lower_check = (entry.title or "").lower()
        pack_keywords = ["complete", "season pack", "boxset", "duology", "trilogy", "full season"]

        if any(kw in title_lower_check for kw in pack_keywords):
            matched.append("season_pack:detected")
            return True

        if re.search(r"\bS\d{1,3}\b(?!\s*E\d)", entry.title or "", re.IGNORECASE):
            if not re.search(r"\bS\d{1,3}\s*E\d", entry.title or "", re.IGNORECASE):
                matched.append("season_pack:regex")
                return True

        return False

    if token in watchlists:
        ok, label = _match_watchlist(token, watchlists[token], parsed, clean_name_lower)
        if ok:
            matched.append(label)
            return True
        return False

    if token == "shows":
        items = config.get_shows()
        ok, label = _match_watchlist("shows", items, parsed, clean_name_lower)
        if ok:
            matched.append(label)
            return True
        return False

    if token == "movies":
        items = config.get_movies()
        ok, label = _match_watchlist("movies", items, parsed, clean_name_lower)
        if ok:
            matched.append(label)
            return True
        return False

    if token in groups:
        group_list = [g.lower() for g in groups[token]]
        if parsed.group and parsed.group.lower() in group_list:
            matched.append(f"group:{parsed.group}({token})")
            return True
        return False

    if token in defs:
        values = defs[token]

        if token.startswith("trk."):
            entry_tracker = (entry.tracker or "").lower()
            for val in values:
                if entry_tracker == val.lower():
                    matched.append(token)
                    return True
            return False

        if token.startswith("cat."):
            entry_cat = (entry.category or "").lower()
            for val in values:
                if val.lower() in entry_cat:
                    matched.append(token)
                    return True
            return False

        for val in values:
            if val.lower() in title_lower:
                matched.append(token)
                return True
        return False

    if token.lower() in title_lower:
        matched.append(token)
        return True

    return False


def _match_watchlist(token: str, items: list[str], parsed: ParsedRelease, clean_name_lower: str) -> tuple[bool, str]:
    token_lower = token.lower()

    if "shows" in token_lower:
        for raw_show in items:
            raw_show = str(raw_show).strip()
            if not raw_show:
                continue

            season_filter = None
            m = re.match(r"^(.*?)\s+[Ss](\d{1,2})$", raw_show)
            if m:
                show_name = m.group(1).strip()
                season_filter = int(m.group(2))
            else:
                show_name = raw_show

            if show_name.lower() in clean_name_lower:
                if season_filter is not None and parsed.season != season_filter:
                    continue
                return True, f"show:{raw_show}"
        return False, ""

    if "movies" in token_lower:
        for raw_movie in items:
            raw_movie = str(raw_movie).strip()
            if not raw_movie:
                continue

            year_filter = None
            m = re.match(r"^(.*?)(?:\s+(\d{4}))?$", raw_movie)
            if m:
                movie_name = (m.group(1) or "").strip()
                if m.group(2):
                    year_filter = int(m.group(2))
            else:
                movie_name = raw_movie

            if movie_name.lower() in clean_name_lower:
                if year_filter is not None and parsed.year != year_filter:
                    continue
                return True, f"movie:{raw_movie}"
        return False, ""

    for item in items:
        item = str(item).strip()
        if item and item.lower() in clean_name_lower:
            return True, f"list:{item}"

    return False, ""