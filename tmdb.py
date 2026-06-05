import time
import logging
import requests
from functools import lru_cache

from config import TMDB_API_KEY

log = logging.getLogger("tmdb")

BASE = "https://api.themoviedb.org/3"
IMG_BASE = "https://image.tmdb.org/t/p/w500"

_cache = {}
_cache_ttl = 86400


def search_movie(name: str, year: int | None = None) -> dict | None:
    if not TMDB_API_KEY:
        return None
    key = f"movie:{name}:{year}"
    cached = _get_cache(key)
    if cached:
        return cached

    params = {"api_key": TMDB_API_KEY, "query": name}
    if year:
        params["year"] = year

    try:
        r = requests.get(f"{BASE}/search/movie", params=params, timeout=10)
        if r.status_code != 200:
            return None
        results = r.json().get("results", [])
        if not results:
            return None
        hit = results[0]
        data = {
            "tmdb_id": hit["id"],
            "title": hit.get("title", name),
            "overview": hit.get("overview", "")[:200],
            "rating": hit.get("vote_average", 0),
            "poster": f"{IMG_BASE}{hit['poster_path']}" if hit.get("poster_path") else "",
            "imdb_id": "",
            "type": "movie",
        }
        imdb = _get_imdb(hit["id"], "movie")
        if imdb:
            data["imdb_id"] = imdb
        _set_cache(key, data)
        return data
    except Exception as e:
        log.error(f"TMDB movie search failed: {e}")
        return None


def search_tv(name: str) -> dict | None:
    if not TMDB_API_KEY:
        return None
    key = f"tv:{name}"
    cached = _get_cache(key)
    if cached:
        return cached

    params = {"api_key": TMDB_API_KEY, "query": name}
    try:
        r = requests.get(f"{BASE}/search/tv", params=params, timeout=10)
        if r.status_code != 200:
            return None
        results = r.json().get("results", [])
        if not results:
            return None
        hit = results[0]
        data = {
            "tmdb_id": hit["id"],
            "title": hit.get("name", name),
            "overview": hit.get("overview", "")[:200],
            "rating": hit.get("vote_average", 0),
            "poster": f"{IMG_BASE}{hit['poster_path']}" if hit.get("poster_path") else "",
            "imdb_id": "",
            "type": "tv",
        }
        imdb = _get_imdb(hit["id"], "tv")
        if imdb:
            data["imdb_id"] = imdb
        _set_cache(key, data)
        return data
    except Exception as e:
        log.error(f"TMDB TV search failed: {e}")
        return None


def lookup(name: str, year: int | None = None, is_tv: bool = False) -> dict | None:
    if is_tv:
        result = search_tv(name)
        if result:
            return result
    result = search_movie(name, year)
    if result:
        return result
    if not is_tv:
        return search_tv(name)
    return None

def lookup_by_imdb(imdb_id: str) -> dict | None:
    if not TMDB_API_KEY or not imdb_id:
        return None

    key = f"imdb:{imdb_id}"
    cached = _get_cache(key)
    if cached:
        return cached

    try:
        r = requests.get(
            f"{BASE}/find/{imdb_id}",
            params={"api_key": TMDB_API_KEY, "external_source": "imdb_id"},
            timeout=10,
        )
        if r.status_code != 200:
            return None

        data = r.json()
        results = data.get("movie_results", []) + data.get("tv_results", [])
        if not results:
            return None

        hit = results[0]
        is_tv = "name" in hit and "title" not in hit

        result = {
            "tmdb_id": hit["id"],
            "title": hit.get("title") or hit.get("name", ""),
            "overview": hit.get("overview", "") or "",
            "rating": hit.get("vote_average", 0),
            "poster": f"{IMG_BASE}{hit['poster_path']}" if hit.get("poster_path") else "",
            "imdb_id": imdb_id,
            "type": "tv" if is_tv else "movie",
        }

        _set_cache(key, result)
        return result
    except Exception as e:
        log.error(f"TMDB IMDB lookup failed: {e}")
        return None

def _get_imdb(tmdb_id: int, media_type: str) -> str:
    try:
        r = requests.get(
            f"{BASE}/{media_type}/{tmdb_id}/external_ids",
            params={"api_key": TMDB_API_KEY}, timeout=10
        )
        if r.status_code == 200:
            return r.json().get("imdb_id", "")
    except Exception:
        pass
    return ""

def get_next_episode(tmdb_id: int) -> dict | None:
    if not TMDB_API_KEY or not tmdb_id:
        return None
    try:
        r = requests.get(
            f"{BASE}/tv/{tmdb_id}",
            params={"api_key": TMDB_API_KEY},
            timeout=10
        )
        if r.status_code != 200:
            return None
        data = r.json()

        next_ep = data.get("next_episode_to_air")
        last_ep = data.get("last_episode_to_air")
        status = data.get("status", "")

        result = {"status": status}

        if next_ep:
            result["next_season"] = next_ep.get("season_number")
            result["next_episode"] = next_ep.get("episode_number")
            result["next_air_date"] = next_ep.get("air_date", "")
            result["next_name"] = next_ep.get("name", "")

        if last_ep:
            result["last_season"] = last_ep.get("season_number")
            result["last_episode"] = last_ep.get("episode_number")
            result["last_air_date"] = last_ep.get("air_date", "")

        return result
    except Exception:
        return None

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