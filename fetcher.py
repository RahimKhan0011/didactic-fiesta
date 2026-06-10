import re
import time
import logging
from email.utils import parsedate_to_datetime

import feedparser
import requests

from models import TorrentEntry

log = logging.getLogger("fetcher")

TL_ID_PATTERN = re.compile(r'/torrent/(\d+)')
SEED_LEECH_PATTERN = re.compile(r'Seeders:\s*(\d+)\s*-\s*Leechers:\s*(\d+)')

AZ_ID_PATTERN = re.compile(r'/torrent/(\d+)-')
AZ_SIZE_PATTERN = re.compile(r'Size.*?:\s*([\d.,]+)\s*(GB|MB|TB|KB)', re.IGNORECASE)
AZ_SEED_PATTERN = re.compile(r'Seed.*?:\s*(\d+)')
AZ_LEECH_PATTERN = re.compile(r'Leech.*?:\s*(\d+)')
AZ_IMDB_PATTERN = re.compile(r'imdb\.com/title/(tt\d+)')
AZ_TMDB_PATTERN = re.compile(r'themoviedb\.org/(?:movie|tv)/(\d+)')

AR_ID_PATTERN = re.compile(r'[?&]id=(\d+)')

FL_ID_PATTERN = re.compile(r'[?&]id=(\d+)')
FL_SIZE_PATTERN = re.compile(r'Size:\s*([\d.,]+)\s*(GB|MB|TB|KB)', re.IGNORECASE)
FL_IMDB_PATTERN = re.compile(r'imdb\.com/title/(tt\d+)')
FL_CAT_PATTERN = re.compile(r'Category:\s*(.+?)(?:\s+Size:)', re.IGNORECASE)
FL_TAG_PATTERN = re.compile(r'\s*\[(FreeLeech|Internal)\]', re.IGNORECASE)

ERAI_TITLE_PATTERN = re.compile(
    r'^\[Torrent\]\s+(.+?)\s*-\s*(\d+)(?:\s+\(HEVC\))?\s+\[(\d+p)\b',
    re.IGNORECASE
)
ERAI_PAGE_PATTERN = re.compile(r'href="([^"]+)"')

IPT_GUID_PATTERN = re.compile(r'/t/(\d+)')
IPT_LINK_PATTERN = re.compile(r'download\.php/(\d+)')
IPT_DESC_PATTERN = re.compile(
    r'^\s*([\d.,]+\s*(?:GB|MB|TB|KB));\s*([^()]+)\s*\(S:(\d+)\s+L:(\d+)\)',
    re.IGNORECASE
)


def fetch_feed(url: str, feed_name: str = "", tracker: str = "tl") -> list[TorrentEntry]:
    start = time.time()

    if tracker == "huno":
        entries = _fetch_huno(url, feed_name)
        took = time.time() - start
        if took >= 5:
            log.warning(f"Slow feed [{feed_name}] took {took:.1f}s ({len(entries)} items)")
        return entries

    entries = []
    try:
        r = requests.get(
            url,
            timeout=(5, 10),
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code != 200:
            log.error(f"Feed HTTP error [{feed_name}]: {r.status_code}")
            return entries

        feed = feedparser.parse(r.content)
    except Exception as e:
        log.error(f"Feed fetch failed [{feed_name}]: {e}")
        return entries

    if feed.bozo and not feed.entries:
        log.warning(f"Bad feed: {feed_name}")
        return entries

    for item in feed.entries:
        if tracker == "avistaz":
            entry = _parse_avistaz(item, feed_name)
        elif tracker == "ar":
            entry = _parse_ar(item, feed_name)
        elif tracker == "fl":
            entry = _parse_fl(item, feed_name)
        elif tracker == "erai":
            entry = _parse_erai(item, feed_name)
        elif tracker == "ipt":
            entry = _parse_ipt(item, feed_name)
        else:
            entry = _parse_tl(item, feed_name)

        if entry:
            entries.append(entry)

    seen_ids = set()
    deduped = []
    for e in entries:
        if e.torrent_id not in seen_ids:
            seen_ids.add(e.torrent_id)
            deduped.append(e)

    took = time.time() - start
    if took >= 5:
        log.warning(f"Slow feed [{feed_name}] took {took:.1f}s ({len(deduped)} items)")

    return deduped

def _parse_tl(item: dict, feed_name: str) -> TorrentEntry | None:
    guid = item.get("guid", item.get("id", ""))
    m = TL_ID_PATTERN.search(guid)
    if not m:
        return None

    title = item.get("title", "").strip()
    if not title:
        return None

    desc = item.get("description", "") or item.get("summary", "")
    seeders, leechers = 0, 0
    sm = SEED_LEECH_PATTERN.search(desc)
    if sm:
        seeders = int(sm.group(1))
        leechers = int(sm.group(2))

    return TorrentEntry(
        torrent_id=int(m.group(1)),
        title=title,
        category=item.get("category", ""),
        download_url=item.get("link", ""),
        page_url=guid,
        seeders=seeders,
        leechers=leechers,
        pub_date=item.get("published", ""),
        pub_timestamp=_parse_date(item.get("published", "")),
        feed_source=feed_name,
        tracker="tl",
    )


def _parse_avistaz(item: dict, feed_name: str) -> TorrentEntry | None:
    guid = item.get("guid", item.get("id", ""))
    m = AZ_ID_PATTERN.search(guid)
    torrent_id = int(m.group(1)) if m else abs(hash(guid)) % 10000000000

    title = item.get("title", "").strip()
    if not title:
        return None

    download_url = ""
    for enc in item.get("enclosures", []):
        href = enc.get("href", "") or enc.get("url", "")
        if href:
            download_url = href
            break

    desc = item.get("description", "") or item.get("summary", "")

    seeders, leechers = 0, 0
    sm = AZ_SEED_PATTERN.search(desc)
    if sm:
        seeders = int(sm.group(1))
    lm = AZ_LEECH_PATTERN.search(desc)
    if lm:
        leechers = int(lm.group(1))

    size_bytes = 0
    cl = item.get("torrent_contentlength", "")
    if cl and str(cl).isdigit():
        size_bytes = int(cl)
    else:
        sz = AZ_SIZE_PATTERN.search(desc)
        if sz:
            size_bytes = _parse_size_str(f"{sz.group(1)} {sz.group(2)}")

    info_hash = item.get("torrent_infohash", "")
    if not info_hash:
        mh = re.search(r'([a-fA-F0-9]{40})', guid)
        if mh:
            info_hash = mh.group(1)

    imdb_id = ""
    im = AZ_IMDB_PATTERN.search(desc)
    if im:
        imdb_id = im.group(1)

    tmdb_id = 0
    tm = AZ_TMDB_PATTERN.search(desc)
    if tm:
        tmdb_id = int(tm.group(1))

    return TorrentEntry(
        torrent_id=torrent_id,
        title=title,
        category=item.get("category", ""),
        download_url=download_url,
        page_url=item.get("link", guid),
        seeders=seeders,
        leechers=leechers,
        pub_date=item.get("published", ""),
        pub_timestamp=_parse_date(item.get("published", "")),
        feed_source=feed_name,
        tracker="avistaz",
        size_bytes=size_bytes,
        info_hash=info_hash,
        imdb_id=imdb_id,
        tmdb_id=tmdb_id,
        uploader=item.get("author", "") or item.get("dc_creator", ""),
    )


def _parse_ar(item: dict, feed_name: str) -> TorrentEntry | None:
    title = item.get("title", "").strip()
    if not title:
        return None

    link = item.get("link", "")
    guid = item.get("guid", item.get("id", ""))

    m = AR_ID_PATTERN.search(link or guid)
    torrent_id = int(m.group(1)) if m else abs(hash(title + guid)) % 10000000000

    page_url = ""
    comments = item.get("comments", "")
    if comments:
        page_url = comments
    else:
        for l in item.get("links", []):
            href = l.get("href", "")
            if "torrents.php?id=" in href:
                page_url = href
                break
    if not page_url:
        page_url = guid

    raw_cat = item.get("category", "")
    category = _clean_ar_category(raw_cat)

    return TorrentEntry(
        torrent_id=torrent_id,
        title=title,
        category=category,
        download_url=link,
        page_url=page_url,
        seeders=0,
        leechers=0,
        pub_date=item.get("published", ""),
        pub_timestamp=_parse_date(item.get("published", "")),
        feed_source=feed_name,
        tracker="ar",
    )


def _parse_fl(item: dict, feed_name: str) -> TorrentEntry | None:
    title = item.get("title", "").strip()
    if not title:
        return None

    link = item.get("link", "")
    m = FL_ID_PATTERN.search(link)
    torrent_id = int(m.group(1)) if m else abs(hash(title + link)) % 10000000000

    clean_title = FL_TAG_PATTERN.sub("", title).strip()

    desc = item.get("description", "") or item.get("summary", "")

    category = ""
    cat_match = FL_CAT_PATTERN.search(desc)
    if cat_match:
        category = cat_match.group(1).strip()

    size_bytes = 0
    sz = FL_SIZE_PATTERN.search(desc)
    if sz:
        size_bytes = _parse_size_str(f"{sz.group(1)} {sz.group(2)}")

    imdb_id = ""
    im = FL_IMDB_PATTERN.search(desc)
    if im:
        imdb_id = im.group(1)

    page_url = f"https://thefl.org/details.php?id={torrent_id}" if torrent_id else ""

    return TorrentEntry(
        torrent_id=torrent_id,
        title=clean_title,
        category=category,
        download_url=link,
        page_url=page_url,
        seeders=0,
        leechers=0,
        pub_date=item.get("published", ""),
        pub_timestamp=_parse_date(item.get("published", "")),
        feed_source=feed_name,
        tracker="fl",
        size_bytes=size_bytes,
        imdb_id=imdb_id,
    )


def _parse_erai(item: dict, feed_name: str) -> TorrentEntry | None:
    raw_title = item.get("title", "").strip()
    if not raw_title:
        return None

    download_url = item.get("link", "")
    infohash = item.get("erai_infohash", "") or ""
    if infohash:
        try:
            torrent_id = int(infohash[:12], 16)
        except Exception:
            torrent_id = abs(hash(infohash)) % 10000000000
    else:
        torrent_id = abs(hash(download_url or raw_title)) % 10000000000

    resolution = item.get("erai_resolution", "") or ""
    infomkv = item.get("erai_infomkv", "") or ""
    size_raw = item.get("erai_size", "") or ""
    size_bytes = _parse_size_str(size_raw) if size_raw else 0
    category_tag = (item.get("erai_category", "") or "").strip()

    page_url = ""
    desc = item.get("description", "") or item.get("summary", "")
    pm = ERAI_PAGE_PATTERN.search(desc)
    if pm:
        page_url = pm.group(1)

    title = raw_title
    if infomkv and resolution and f"[{resolution}" not in raw_title:
        title = f"{raw_title} [{resolution} {infomkv}]"

    if category_tag and category_tag not in title:
        title = f"{title} {category_tag}"

    return TorrentEntry(
        torrent_id=torrent_id,
        title=title,
        category="Anime",
        download_url=download_url,
        page_url=page_url,
        seeders=0,
        leechers=0,
        pub_date=item.get("published", ""),
        pub_timestamp=_parse_date(item.get("published", "")),
        feed_source=feed_name,
        tracker="erai",
        size_bytes=size_bytes,
        info_hash=infohash,
        uploader="Erai-raws",
    )

def _parse_ipt(item: dict, feed_name: str) -> TorrentEntry | None:
    title = item.get("title", "").strip()
    if not title:
        return None

    link = item.get("link", "")
    guid = item.get("guid", item.get("id", ""))

    torrent_id = 0
    m = IPT_GUID_PATTERN.search(guid)
    if m:
        torrent_id = int(m.group(1))
    else:
        m = IPT_LINK_PATTERN.search(link)
        if m:
            torrent_id = int(m.group(1))
    if not torrent_id:
        torrent_id = abs(hash(title + guid + link)) % 10000000000

    desc = item.get("description", "") or item.get("summary", "")

    size_bytes = 0
    category = ""
    seeders = 0
    leechers = 0

    dm = IPT_DESC_PATTERN.search(desc)
    if dm:
        size_bytes = _parse_size_str(dm.group(1))
        category = dm.group(2).strip()
        seeders = int(dm.group(3))
        leechers = int(dm.group(4))

    download_url = link
    for enc in item.get("enclosures", []):
        href = enc.get("href", "") or enc.get("url", "")
        if href:
            download_url = href
            break

    page_url = guid

    return TorrentEntry(
        torrent_id=torrent_id,
        title=title,
        category=category,
        download_url=download_url,
        page_url=page_url,
        seeders=seeders,
        leechers=leechers,
        pub_date=item.get("published", ""),
        pub_timestamp=_parse_date(item.get("published", "")),
        feed_source=feed_name,
        tracker="ipt",
        size_bytes=size_bytes,
    )


def _fetch_huno(url: str, feed_name: str) -> list[TorrentEntry]:
    entries = []
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            log.error(f"HUNO API error {r.status_code}")
            return entries
        data = r.json().get("data", [])
    except Exception as e:
        log.error(f"HUNO fetch failed: {e}")
        return entries

    for item in data:
        entry = _parse_huno(item, feed_name)
        if entry:
            entries.append(entry)

    log.debug(f"Fetched {len(entries)} from {feed_name}")
    return entries


def _parse_huno(item: dict, feed_name: str) -> TorrentEntry | None:
    attrs = item.get("attributes", {})
    if not attrs:
        return None

    torrent_id = int(item.get("id", 0))
    if not torrent_id:
        return None

    title = attrs.get("name", "").strip()
    if not title:
        return None

    cat = attrs.get("category", "")
    if cat == "TV":
        cat = "TV-Show"

    imdb_raw = attrs.get("imdb_id", "")
    imdb_id = ""
    if imdb_raw and str(imdb_raw) != "0":
        imdb_id = f"tt{imdb_raw}" if not str(imdb_raw).startswith("tt") else str(imdb_raw)

    tmdb_raw = attrs.get("tmdb_id", "")
    tmdb_id = int(tmdb_raw) if tmdb_raw and str(tmdb_raw) != "0" else 0

    pub_ts = 0.0
    created = attrs.get("created_at", "")
    if created:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            pub_ts = dt.timestamp()
        except Exception:
            pass

    return TorrentEntry(
        torrent_id=torrent_id,
        title=title,
        category=cat,
        download_url=attrs.get("download_link", ""),
        page_url=attrs.get("details_link", ""),
        seeders=int(attrs.get("seeders", 0)),
        leechers=int(attrs.get("leechers", 0)),
        pub_date=created,
        pub_timestamp=pub_ts,
        feed_source=feed_name,
        tracker="huno",
        size_bytes=int(attrs.get("size", 0)),
        info_hash="",
        imdb_id=imdb_id,
        tmdb_id=tmdb_id,
        uploader=attrs.get("uploader", ""),
    )


def _clean_ar_category(raw: str) -> str:
    if not raw:
        return ""
    cleaned = re.sub(r',?\s*tt\d+', '', raw)
    cleaned = re.sub(r',?\s*\d{4,}', '', cleaned)
    cleaned = cleaned.strip().strip(",").strip()
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    if not parts:
        return raw
    return parts[0] if len(parts) == 1 else ", ".join(parts[:2])


def _parse_size_str(size_str: str) -> int:
    if not size_str:
        return 0
    m = re.search(r'([\d.,]+)\s*(TB|GB|MB|KB)', size_str, re.IGNORECASE)
    if not m:
        return 0
    val = float(m.group(1).replace(",", ""))
    unit = m.group(2).upper()
    mult = {
        "TB": 1099511627776,
        "GB": 1073741824,
        "MB": 1048576,
        "KB": 1024,
    }
    return int(val * mult.get(unit, 1))


def _parse_date(pub_str: str) -> float:
    if not pub_str:
        return 0.0
    try:
        dt = parsedate_to_datetime(pub_str)
        return dt.timestamp()
    except Exception:
        return 0.0