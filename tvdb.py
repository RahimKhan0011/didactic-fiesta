import re
import time
import logging
import requests

log = logging.getLogger("tvdb")

BASE = "https://api4.thetvdb.com/v4"

_token = ""
_token_expiry = 0
_cache = {}
_cache_ttl = 86400


def _norm(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', (s or "").lower())


def _to_int(v) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def _extract_aliases(raw) -> list[str]:
    out = []
    if not isinstance(raw, list):
        return out

    for item in raw:
        if isinstance(item, str):
            s = item.strip()
            if s:
                out.append(s)
        elif isinstance(item, dict):
            s = (
                item.get("name")
                or item.get("title")
                or item.get("value")
                or ""
            ).strip()
            if s:
                out.append(s)

    seen = set()
    uniq = []
    for x in out:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq


def _score_result(query: str, hit: dict) -> int:
    q = _norm(query)
    if not q:
        return 0

    names = []
    primary = (hit.get("name") or "").strip()
    if primary:
        names.append(primary)
    names.extend(_extract_aliases(hit.get("aliases")))

    best = 0
    for name in names:
        n = _norm(name)
        if not n:
            continue
        if n == q:
            best = max(best, 100)
        elif n.startswith(q) or q.startswith(n):
            best = max(best, 90)
        elif q in n or n in q:
            best = max(best, 75)

    return best


def _get_token(api_key: str) -> str:
    global _token, _token_expiry

    if _token and time.time() < _token_expiry:
        return _token

    try:
        r = requests.post(
            f"{BASE}/login",
            json={"apikey": api_key},
            timeout=10,
        )
        if r.status_code != 200:
            log.error(f"TVDB login failed: {r.status_code}")
            return ""

        data = r.json().get("data", {})
        _token = data.get("token", "")
        _token_expiry = time.time() + 82800
        return _token

    except Exception as e:
        log.error(f"TVDB login error: {e}")
        return ""


def _headers(api_key: str) -> dict:
    token = _get_token(api_key)
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _get_cache(key: str):
    if key in _cache:
        data, ts = _cache[key]
        if time.time() - ts < _cache_ttl:
            return data
        del _cache[key]
    return None


def _set_cache(key: str, data):
    _cache[key] = (data, time.time())
    if len(_cache) > 500:
        oldest = sorted(_cache.items(), key=lambda x: x[1][1])[:100]
        for k, _ in oldest:
            del _cache[k]


def search_series(name: str, api_key: str) -> dict | None:
    if not api_key:
        return None

    cache_key = f"tvdb_search:{name.lower()}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    headers = _headers(api_key)
    if not headers:
        return None

    try:
        r = requests.get(
            f"{BASE}/search",
            params={"query": name, "type": "series"},
            headers=headers,
            timeout=10,
        )
        if r.status_code != 200:
            return None

        results = r.json().get("data", [])
        if not results:
            return None

        best_hit = None
        best_score = -1

        for hit in results:
            if not isinstance(hit, dict):
                continue
            score = _score_result(name, hit)
            if score > best_score:
                best_score = score
                best_hit = hit

        if not best_hit:
            return None

        data = {
            "tvdb_id": _to_int(best_hit.get("tvdb_id") or best_hit.get("id")),
            "name": best_hit.get("name", name),
            "aliases": _extract_aliases(best_hit.get("aliases")),
            "year": best_hit.get("year", ""),
            "image": best_hit.get("image_url") or best_hit.get("image") or "",
        }

        if not data["tvdb_id"]:
            return None

        _set_cache(cache_key, data)
        return data

    except Exception as e:
        log.error(f"TVDB search failed: {e}")
        return None


def get_series_artwork(tvdb_id: int, api_key: str) -> str:
    if not api_key or not tvdb_id:
        return ""

    cache_key = f"tvdb_art:{tvdb_id}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    headers = _headers(api_key)
    if not headers:
        return ""

    try:
        r = requests.get(
            f"{BASE}/series/{tvdb_id}",
            headers=headers,
            timeout=10,
        )
        if r.status_code != 200:
            return ""

        data = r.json().get("data", {})
        image = data.get("image", "")

        if image:
            _set_cache(cache_key, image)
            return image

        return ""

    except Exception as e:
        log.error(f"TVDB artwork fetch failed: {e}")
        return ""


def get_series_episodes(tvdb_id: int, api_key: str) -> list[dict] | None:
    if not api_key or not tvdb_id:
        return None

    cache_key = f"tvdb_eps:{tvdb_id}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    headers = _headers(api_key)
    if not headers:
        return None

    all_episodes = []
    page = 0

    try:
        while True:
            r = requests.get(
                f"{BASE}/series/{tvdb_id}/episodes/default",
                params={"page": page},
                headers=headers,
                timeout=15,
            )
            if r.status_code != 200:
                break

            body = r.json()
            data = body.get("data", {})
            episodes = data.get("episodes", [])
            if not episodes:
                break

            for ep in episodes:
                season_num = ep.get("seasonNumber")
                ep_num = ep.get("number")

                if season_num is None or ep_num is None:
                    continue
                if season_num == 0:
                    continue

                all_episodes.append({
                    "season": _to_int(season_num),
                    "episode": _to_int(ep_num),
                    "absolute_number": _to_int(ep.get("absoluteNumber")) or None,
                    "name": ep.get("name", ""),
                    "aired": ep.get("aired", ""),
                })

            next_link = body.get("links", {}).get("next")
            if not next_link:
                break

            page += 1
            if page > 50:
                break

        if all_episodes:
            _set_cache(cache_key, all_episodes)
            return all_episodes

        return None

    except Exception as e:
        log.error(f"TVDB episodes fetch failed: {e}")
        return None


def resolve_absolute_episode(tvdb_id: int, absolute_ep: int, api_key: str) -> tuple[int, int] | None:
    if not api_key or not tvdb_id or not absolute_ep:
        return None

    cache_key = f"tvdb_abs:{tvdb_id}:{absolute_ep}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    episodes = get_series_episodes(tvdb_id, api_key)
    if not episodes:
        return None

    for ep in episodes:
        if ep.get("absolute_number") == absolute_ep:
            result = (ep["season"], ep["episode"])
            _set_cache(cache_key, result)
            return result

    eps_sorted = sorted(episodes, key=lambda e: (e["season"], e["episode"]))
    if absolute_ep <= len(eps_sorted):
        ep = eps_sorted[absolute_ep - 1]
        result = (ep["season"], ep["episode"])
        _set_cache(cache_key, result)
        return result

    return None


def resolve_by_name(name: str, absolute_ep: int, api_key: str) -> tuple[int, int] | None:
    series = search_series(name, api_key)
    if not series or not series.get("tvdb_id"):
        return None

    return resolve_absolute_episode(series["tvdb_id"], absolute_ep, api_key)