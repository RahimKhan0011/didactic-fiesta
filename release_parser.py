import re
from typing import Optional
from models import ParsedRelease, ContentType

RESOLUTIONS = ["2160p", "1080p", "1080i", "720p", "576p", "480p"]

CODECS = [
    "x265", "x264",
    "H.265", "H265", "H 265",
    "H.264", "H264", "H 264",
    "h265", "h264",
    "HEVC", "AVC", "XviD", "AV1", "VP9",
    "MPEG-2", "VC-1",
]

AUDIO_PATTERNS = [
    "DTS-HD MA 7.1", "DTS-HD MA 5.1", "DTS-HD MA 2.0",
    "DTS-HD MA", "DTS-HD.MA", "DTS-HD",
    "TrueHD Atmos 7.1", "TrueHD Atmos",
    "TrueHD 7.1", "TrueHD 5.1", "TrueHD",
    "DDP Atmos 7.1", "DDP Atmos 5.1", "DDP Atmos",
    "DD+ Atmos 7.1", "DD+ Atmos 5.1", "DD+ Atmos",
    "DD+Atmos",
    "DDP7.1", "DDP5.1", "DDP 5 1", "DDP2.0", "DDP",
    "DD+ 7.1", "DD+ 5.1", "DD+ 5 1", "DD+ 2.0", "DD+ 2 0", "DD+",
    "DD5.1", "DD5 1", "DD2.0", "DD 5 1", "DD 2 0",
    "Atmos",
    "AAC2.0", "AAC2 0", "AAC5.1", "AAC 2 0", "AAC",
    "FLAC 5.1", "FLAC 2.0", "FLAC",
    "LPCM", "PCM",
    "EAC3", "EAC-3",
    "AC3", "MP3", "DTS",
]

HDR_TAGS = [
    "DoVi HDR10+", "DoVi HDR10", "DoVi",
    "DV HDR10+", "DV HDR10", "DV HDR",
    "Dolby Vision",
    "HDR10+", "HDR10", "HDR",
    "HLG", "PQ",
    "10Bit", "10bit",
    "SDR",
]

RELEASE_TAGS = [
    "REPACK", "PROPER", "RERIP", "INTERNAL", "REAL",
    "COMPLETE", "DUOLOGY", "TRILOGY", "MULTi", "DUAL",
    "Directors Cut", "Criterion Collection", "UNCUT",
    "EXTENDED", "THEATRICAL", "REMASTERED"
]

GAME_GROUPS = [
    "rune", "kaos", "dodi", "fitgirl", "plaza", "codex",
    "tenoke", "flt", "skidrow", "razor1911", "goldberg",
    "doge", "suxxors", "darksiders"
]

SERVICE_TOKENS = {
    "AMZN": "AMZN", "AMAZON": "AMZN",
    "NF": "NF", "NETFLIX": "NF",
    "ATVP": "ATVP", "ATV+": "ATVP", "APPLETV": "ATVP",
    "DSNP": "DSNP", "DSNY": "DSNP", "DISNEY+": "DSNP", "DISNEY": "DSNP",
    "HMAX": "HMAX", "HBO": "HMAX", "HBOMAX": "HMAX",
    "PCOK": "PCOK", "PEACOCK": "PCOK",
    "PMTP": "PMTP", "PARAMOUNT+": "PMTP", "PARAMOUNT": "PMTP",
    "HULU": "HULU",
    "CR": "CR", "CRUNCHYROLL": "CR",
    "FUNI": "FUNI", "FUNIMATION": "FUNI",
    "STAN": "STAN",
    "CRAV": "CRAV", "CRAVE": "CRAV",
    "MUBI": "MUBI",
    "CC": "CC", "CRITERION": "CC",
    "HTSR": "HTSR", "HOTSTAR": "HTSR",
    "HS": "HS",
    "IP": "iP", "IPLAYER": "iP", "BBC": "BBC",
    "ALL4": "ALL4", "CHANNEL4": "ALL4",
    "IT": "iT", "ITUNES": "iT",
    "NOW": "NOW",
    "VIKI": "VIKI",
    "AHA": "AHA",
    "SNXT": "SNXT", "SUNNXT": "SNXT",
    "KCW": "KCW", "KOCOWA": "KCW",
    "WTV": "WTV", "WARHAMMERTV": "WTV",
    "JHS": "JHS", "JIOHOTSTAR": "JHS",
    "ROKU": "ROKU",
    "TUBI": "TUBI",
    "BINGE": "BINGE",
    "BILI": "BILI", "BILIBILI": "BILI",
    "IQ": "IQ", "IQIYI": "IQ",
    "WAVVE": "WAVVE",
    "TVING": "TVING",
    "TVN": "TVN",
    "TEN": "TEN",
    "LBXD": "LBXD",
    "HIDIVE": "HIDIVE",
    "HIDI": "HIDIVE",
}

SOURCE_PATTERNS = [
    ("UHD BluRay REMUX", ["UHD BLURAY REMUX", "UHD BLU RAY REMUX"], "REMUX"),
    ("BluRay REMUX", ["BLURAY REMUX", "BLU RAY REMUX"], "REMUX"),
    ("REMUX", ["REMUX"], "REMUX"),
    ("UHD BluRay", ["UHD BLURAY", "UHD BLU RAY"], "BluRay"),
    ("WEB-DL", ["WEB-DL", "WEB DL", "WEBDL"], "WEB-DL"),
    ("WEBRip", ["WEBRIP", "WEB RIP"], "WEBRip"),
    ("BluRay", ["BLURAY", "BLU RAY", "BDRIP", "BRRIP"], "BluRay"),
    ("HDTV", ["HDTV"], "HDTV"),
    ("PDTV", ["PDTV"], "HDTV"),
    ("DVDRip", ["DVDRIP", "DVD RIP"], "DVD"),
    ("DVD-R", ["DVD-R", "DVD R"], "DVD"),
    ("SDTV", ["SDTV"], "HDTV"),
    ("HDRip", ["HDRIP", "HD RIP"], "WEBRip"),
    ("WEB", ["WEB"], "WEB"),
]

GAME_CATS = ["PC", "Nintendo Switch", "PS5", "PS4", "Xbox", "Mac", "Games", "PS", "Switch"]

ANIME_GROUP_PATTERN = re.compile(
    r'^\[([^\]]+)\]\s*(.+?)(?:\s*-\s*(\d+)(?:v(\d+))?)?\s*(?:\((\d+p)\))?\s*(?:\[([A-F0-9]+)\])?$',
    re.IGNORECASE
)

ANIME_SXE_AFTER_DASH_PATTERN = re.compile(
    r'^\[([^\]]+)\]\s*(.+?)\s*-\s*S(\d{1,2})E(\d{1,3})(?:\s|$)',
    re.IGNORECASE
)

ANIME_S_AFTER_NAME_DASH_EP_PATTERN = re.compile(
    r'^\[([^\]]+)\]\s*(.+?)\s+S(\d{1,2})\s*-\s*(\d{1,3})(?:\s|$)',
    re.IGNORECASE
)

FOREIGN_EPISODE_PATTERN = re.compile(
    r'^(?P<name>.+?)\s+(?P<episode>\d{1,4})\s*(?:Blm|Bölüm|Bolum)\b(?:.*)?$',
    re.IGNORECASE,
)
SEASON_EP_PATTERN = re.compile(r'S(\d{1,3})(?:E(\d{1,3})(?:-?E?(\d{1,3}))?)?', re.IGNORECASE)
EP_ONLY_PATTERN = re.compile(r'\bE(\d{1,4})(?:-?E?(\d{1,4}))?\b', re.IGNORECASE)
YEAR_PATTERN = re.compile(r'(?:^|[\s.(])(\d{4})(?:[\s.)]|$)')
GAME_VERSION_PATTERN = re.compile(r'\b[Vv]?(\d+(?:[._ ]\d+)+)\b')
SPORTS_PATTERN = re.compile(r'(?:MLB|NFL|NBA|NHL|UFC|WWE|F1|MotoGP|Boxing)\s+\d{4}', re.IGNORECASE)
DAILY_SHOW_PATTERN = re.compile(r'^(.+?)\s+(\d{4})\s+(\d{2})\s+(\d{2})(?:\s+(.+?))?\s+\d+p', re.IGNORECASE)
DAILY_SHOW_DOT_PATTERN = re.compile(r'^(.+?)\.(\d{4})\.(\d{2})\.(\d{2})(?:\.(.+?))?\.\d+p', re.IGNORECASE)
HUNO_TITLE_PATTERN = re.compile(r'^(.+?)\s+\((\d{4})\)\s+\((\d{3,4}p\s.+)\)$')

AR_PREFIX_PATTERN = re.compile(
    r'^(?:Tv(?:Pack)?(?:UHD|HD|SD)?|Movie(?:UHD|HD|SD|4K)?|Anime(?:UHD|HD|SD)?|Games\w*|AppsPC|Music(?:HD|SD)?|EBooks|AudioBooks)\s+\d+\s+\d+\s+',
    re.IGNORECASE
)

FL_TAG_PATTERN = re.compile(r'\s*\[(FreeLeech|Internal)\]', re.IGNORECASE)

ERAI_PREFIX_PATTERN = re.compile(r'^\[(?:Torrent|Erai-raws)\]\s*', re.IGNORECASE)
ERAI_STATE_PATTERN = re.compile(r'\[(Airing|Encoded)\]\s*$', re.IGNORECASE)

LEADING_LANGUAGE_TAG_PATTERN = re.compile(
    r'^\[(?:(?:English|Turkish|Japanese|Korean|Chinese|Yue|Cantonese|Hindi|Arabic|Spanish|French|German|Italian|Portuguese|Russian|Multi|Mandarin|Thai|Vietnamese|Indonesian|Malay|Tamil|Telugu)\s*)+\]\s*',
    re.IGNORECASE,
)

ANIME_TRAILING_EP_PATTERN = re.compile(
    r'^(?P<name>.+?)(?:\s+\((?P<year>\d{4})\))?\s+(?P<episode>\d{1,4})(?:v(?P<version>\d+))?(?:\s*\((?P<tech>[^)]*)\))?$',
    re.IGNORECASE,
)

ERAI_MAIN_PATTERN = re.compile(
    r'^(?P<name>.+?)'
    r'(?:\s+(?:(?P<season1>\d+)(?:st|nd|rd|th)\s+Season|Season\s+(?P<season2>\d+)|S(?P<season3>\d+)|Part\s+(?P<season4>\d+)))?'
    r'\s*-\s*(?P<episode>\d+)(?:v(?P<version>\d+))?'
    r'(?:\s+\((?P<codec_hint>[^)]+)\))?\s+'
    r'\[(?P<res>\d+p)\s+(?P<service>[A-Z0-9+]+)\s+(?P<source>WEB-DL|WEBRip|WEB)\s+(?P<codec>AVC|HEVC|EAC-3|AAC)?\s*(?P<audio>[A-Z0-9.+-]*)\]',
    re.IGNORECASE
)

ERAI_IPT_PATTERN = re.compile(
    r'^(?P<name>.+?)'
    r'(?:\s+(?:(?P<season1>\d+)(?:st|nd|rd|th)\s+Season|Season\s+(?P<season2>\d+)|S(?P<season3>\d+)|Part\s+(?P<season4>\d+)))?'
    r'\s*-\s*(?P<episode>\d+)(?:v(?P<version>\d+))?'
    r'(?:\s+\((?P<codec_hint>[^)]+)\))?\s+'
    r'\[(?P<res>\d+p)\s+(?P<service>[A-Z0-9+]+)\s+(?P<source>WEB-DL|WEBRip|WEB)\s+(?P<codec>AVC|HEVC|EAC-3|AAC)?\s*(?P<audio>[A-Z0-9.+-]*)\]'
    r'(?:\[MultiSub\])?',
    re.IGNORECASE
)

ERAI_PREFIX_CAPTURE_PATTERN = re.compile(r'^\[([^\]]+)\]\s*', re.IGNORECASE)

ANIME_MOVIE_SUFFIX_PATTERN = re.compile(
    r'\s*-\s*(Movie|Special(?: Episode)?|OVA|ONA|Movie or Special Episode)\s*$',
    re.IGNORECASE,
)


def parse(title: str, category: str = "") -> ParsedRelease:
    p = ParsedRelease(raw_title=title)
    raw_title = title.strip()
    title_clean = raw_title

    title_clean = AR_PREFIX_PATTERN.sub("", title_clean).strip()
    title_clean = FL_TAG_PATTERN.sub("", title_clean).strip()
    title_clean = re.sub(r'^\[REQ\]\s*', '', title_clean, flags=re.IGNORECASE).strip()
    erai_candidate = title_clean

    erai = _try_erai(erai_candidate)
    if erai:
        _build_keys(erai)
        return erai

    erai_ipt = _try_erai_ipt(erai_candidate)
    if erai_ipt:
        _build_keys(erai_ipt)
        return erai_ipt

    for _ in range(8):
        stripped = LEADING_LANGUAGE_TAG_PATTERN.sub("", title_clean).strip()
        if stripped == title_clean:
            break
        title_clean = stripped

    title_clean = re.sub(
        r'\[(?:(?:English|Japanese|Korean|Chinese|Yue|Cantonese|Hindi|Turkish|Arabic|Spanish|French|German|Italian|Portuguese|Russian|Multi|Mandarin|Thai|Vietnamese|Indonesian|Malay|Tamil|Telugu)\s*)+(?:Dub|Sub|Audio|Dubbed|Subbed)?\]',
        '',
        title_clean,
        flags=re.IGNORECASE,
    ).strip()

    title_clean = re.sub(
        r'\[(?:Dual\s*Audio|Multi\s*Audio|Multi\s*Sub)\]',
        '',
        title_clean,
        flags=re.IGNORECASE,
    ).strip()

    title_clean = re.sub(
        r'\((?:AMZN|NF|CR|HIDIVE|FUNI|BILI|DSNP|ATVP|HMAX|PCOK|PMTP)\)',
        '',
        title_clean,
        flags=re.IGNORECASE,
    ).strip()

    title_clean = re.sub(
        r'\((?:Multi|REPACK|PROPER|RERIP|Chinese Audio|Japanese Audio|English Audio|Dual Audio)\)',
        '',
        title_clean,
        flags=re.IGNORECASE,
    ).strip()

    title_clean = re.sub(r'\[(?:[a-z]{2}(?:-[a-z]{2})?)\]', '', title_clean).strip()
    title_clean = re.sub(r'\s+', ' ', title_clean).strip()

    bracket_tech = re.search(
        r'(\[(?:[A-Z0-9+]+\s+)?(?:WEB-DL|WEBRip|WEB|HDTV)\s+\d+p\s+[A-Z0-9\s.+-]+\])|'
        r'(\[\d+p\s+[A-Z0-9+]+\s+(?:WEB-DL|WEBRip|WEB|HDTV)\s+[A-Z0-9\s.+-]+\])',
        title_clean,
        re.IGNORECASE,
    )
    if bracket_tech:
        tech = bracket_tech.group(0)[1:-1]
        title_clean = title_clean[:bracket_tech.start()].strip() + " " + tech
        title_clean = re.sub(r'\s+', ' ', title_clean).strip()

    huno_match = HUNO_TITLE_PATTERN.match(title_clean)
    if huno_match:
        p = _parse_huno_title(title_clean, huno_match, category)
        _detect_service(p, title_clean)
        _build_keys(p)
        return p

    anime = _try_anime(title_clean)
    if anime:
        _detect_service(anime, title_clean)
        _build_keys(anime)
        return anime

    daily = DAILY_SHOW_PATTERN.match(title_clean)
    if daily:
        p = _parse_daily(title_clean, daily, category)
        _detect_service(p, title_clean)
        _build_keys(p)
        return p

    daily_dot = DAILY_SHOW_DOT_PATTERN.match(title_clean)
    if daily_dot:
        p = _parse_daily_dot(title_clean, daily_dot, category)
        _detect_service(p, title_clean)
        _build_keys(p)
        return p

    foreign_ep = FOREIGN_EPISODE_PATTERN.match(title_clean)
    if foreign_ep:
        p = _parse_foreign_episode(title_clean, foreign_ep, category)
        _detect_service(p, title_clean)
        _build_keys(p)
        return p

    if SPORTS_PATTERN.search(title_clean):
        p = _parse_sports(title_clean, category)
        _build_keys(p)
        return p

    cat_lower = category.lower()
    group_lower = _extract_group(title_clean).lower()
    is_ar_game = bool(re.match(r'^Games\w*\s+\d+\s+\d+\s+', raw_title, re.IGNORECASE))

    if group_lower in GAME_GROUPS:
        p = _parse_game(title_clean, category)
        _build_keys(p)
        return p

    if any(g.lower() in cat_lower for g in GAME_CATS) or is_ar_game:
        p = _parse_game(title_clean, category)
        _build_keys(p)
        return p

    p = _parse_standard(title_clean, category)
    _detect_service(p, title_clean)
    _build_keys(p)
    return p


def _try_erai(title: str) -> Optional[ParsedRelease]:
    pm = ERAI_PREFIX_CAPTURE_PATTERN.match(title)
    prefix_group = pm.group(1).strip() if pm else "Erai-raws"

    clean = ERAI_PREFIX_PATTERN.sub("", title).strip()

    state = ""
    sm = ERAI_STATE_PATTERN.search(clean)
    if sm:
        state = sm.group(1)
        clean = clean[:sm.start()].strip()

    subs = re.sub(r'\[(?:[a-z]{2}(?:-[a-z]{2})?\s*)+\]', '', clean, flags=re.IGNORECASE).strip()
    subs = re.sub(r'\[MultiSub\]', '', subs, flags=re.IGNORECASE).strip()
    subs = re.sub(r'\[[A-F0-9]{8}\]', '', subs).strip()

    m = ERAI_MAIN_PATTERN.match(subs)
    if m:
        return _build_erai_parsed(title, m, state, prefix_group)

    return None


def _try_erai_ipt(title: str) -> Optional[ParsedRelease]:
    pm = ERAI_PREFIX_CAPTURE_PATTERN.match(title)
    prefix_group = pm.group(1).strip() if pm else "Erai-raws"

    clean = ERAI_PREFIX_PATTERN.sub("", title).strip()

    subs = re.sub(r'\[(?:[a-z]{2}(?:-[a-z]{2})?\s*)+\]', '', clean, flags=re.IGNORECASE).strip()
    subs = re.sub(r'\[MultiSub\]', '', subs, flags=re.IGNORECASE).strip()
    subs = re.sub(r'\[[A-F0-9]{8}\]', '', subs).strip()

    m = ERAI_IPT_PATTERN.match(subs)
    if m:
        return _build_erai_parsed(title, m, "", prefix_group)

    return None


def _build_erai_parsed(title: str, m, state: str, group_name: str = "Erai-raws") -> ParsedRelease:
    p = ParsedRelease(raw_title=title)
    p.group = group_name
    p.clean_name = m.group("name").strip().rstrip("-").strip()

    season = m.group("season1") or m.group("season2") or m.group("season3") or m.group("season4")
    if season:
        p.season = int(season)

    ep = m.group("episode")
    if ep:
        p.episode = int(ep)

    if p.season is None and p.episode is not None:
        p.season = 1

    p.content_type = ContentType.ANIME_EP
    p.resolution = m.group("res") or ""
    p.service_code = (m.group("service") or "").upper()

    source_raw = m.group("source") or ""
    p.source = source_raw
    if source_raw.upper() in ("WEB-DL", "WEBDL"):
        p.source_family = "WEB-DL"
    elif source_raw.upper() == "WEBRIP":
        p.source_family = "WEBRip"
    elif source_raw.upper() == "WEB":
        p.source_family = "WEB"
    else:
        p.source_family = source_raw

    version = m.group("version") or ""
    codec_hint = (m.group("codec_hint") or "").strip()

    if not version:
        vm = re.fullmatch(r'V(\d+)', codec_hint, re.IGNORECASE)
        if vm:
            version = vm.group(1)
            codec_hint = ""

    if codec_hint.upper() not in ("HEVC", "AVC", "X265", "X264", "H264", "H265"):
        codec_hint = ""

    codec = m.group("codec") or codec_hint
    audio = m.group("audio") or ""

    if codec.upper() in ("EAC-3", "EAC3"):
        p.audio = codec
        p.codec = ""
    else:
        p.codec = codec
        p.audio = audio

    if version:
        p.tags.append(f"v{version}")
        p.is_repack = True

    if state:
        p.tags.append(state)

    return p


def _build_erai_simple(title: str, m, state: str, group_name: str = "Erai-raws") -> ParsedRelease:
    p = ParsedRelease(raw_title=title)
    p.group = group_name

    raw_name = m.group("name").strip()
    p.clean_name = raw_name

    ep = m.group("episode")
    if ep:
        p.episode = int(ep)

    p.season = 1
    p.content_type = ContentType.ANIME_EP
    p.resolution = m.group("res") or ""

    source_raw = m.group("source") or "WEB"
    p.source = source_raw
    if source_raw.upper() in ("WEB-DL", "WEBDL"):
        p.source_family = "WEB-DL"
    elif source_raw.upper() == "WEBRIP":
        p.source_family = "WEBRip"
    else:
        p.source_family = "WEB"

    audio = m.group("audio") or ""
    if audio:
        p.audio = audio

    if state:
        p.tags.append(state)

    return p


def _detect_service(p: ParsedRelease, title: str):
    title_upper = title.upper().replace(".", " ").replace("-", " ").replace("_", " ")
    tokens = title_upper.split()

    for token in tokens:
        if token in SERVICE_TOKENS:
            p.service_code = SERVICE_TOKENS[token]
            return

    for token in tokens:
        token_clean = token.strip("()")
        if token_clean in SERVICE_TOKENS:
            p.service_code = SERVICE_TOKENS[token_clean]
            return


def _find_source(title: str) -> tuple[str, str]:
    raw = title.upper()
    normalized = raw.replace(".", " ").replace("-", " ")

    for label, patterns, family in SOURCE_PATTERNS:
        for pat in patterns:
            if pat in raw or pat in normalized:
                return label, family

    return "", ""


def _find_audio(title: str) -> str:
    t = title.replace(".", " ").replace("-", " ").replace("_", " ")
    t_spaced = " " + t + " "
    for a in AUDIO_PATTERNS:
        a_spaced = a.replace(".", " ")
        if a_spaced in t_spaced or a in t_spaced:
            return a
    return ""


def _find_match(title: str, options: list[str]) -> str:
    title_check = title.upper().replace(".", " ").replace("-", " ")
    for opt in options:
        opt_check = opt.upper().replace(".", " ")
        if opt_check in title_check:
            return opt
    for opt in options:
        if opt.upper() in title.upper():
            return opt
    return ""


def _extract_group(title: str) -> str:
    title = title.strip()

    skip = {
        "req", "mp4", "mkv", "avi", "264", "265", "hevc", "avc", "web", "webrip",
        "webdl", "web-dl", "bluray", "remux", "dl", "dts", "aac", "ac3", "eac3",
        "eac-3", "dd", "ddp", "dd+", "truehd", "atmos", "hdr", "sdr", "dv",
        "hdr10", "hdr10+", "1080p", "2160p", "720p", "480p", "complete",
        "proper", "repack", "final"
    }

    def _valid(grp: str) -> str:
        grp = (grp or "").strip().strip("-").strip()
        if not grp:
            return ""

        gl = grp.lower()
        if gl in skip:
            return ""

        if re.fullmatch(r's\d{1,3}', grp, re.IGNORECASE):
            return ""
        if re.fullmatch(r'e\d{1,4}', grp, re.IGNORECASE):
            return ""
        if re.fullmatch(r's\d{1,3}e\d{1,4}', grp, re.IGNORECASE):
            return ""
        if re.fullmatch(r'\d{3,4}p', grp, re.IGNORECASE):
            return ""

        if re.fullmatch(r'(?:aac|ac3|eac3|eac-3|dd|ddp|dd\+|truehd|atmos)(?:[ .]?\d(?:[ .]?\d)?)?', grp, re.IGNORECASE):
            return ""

        return grp

    m = re.match(r'^\[([^\]]+)\]', title)
    if m:
        grp = _valid(m.group(1))
        if grp:
            return grp

    m = re.search(r'-\s*([A-Za-z0-9@]+(?:\s+[A-Za-z0-9@]+)*)\s*$', title)
    if m:
        grp = _valid(m.group(1))
        if grp:
            return grp

    m = re.search(r'\s([A-Za-z][A-Za-z0-9@]{2,})\s*$', title)
    if m:
        grp = _valid(m.group(1))
        if grp:
            return grp

    return ""

def _get_release_revision(p: ParsedRelease) -> str:
    for tag in p.tags:
        m = re.fullmatch(r'v(\d+)', str(tag).strip(), re.IGNORECASE)
        if m:
            return f"v{m.group(1)}"

    if p.is_repack:
        return "repack"
    if p.is_proper:
        return "proper"

    return ""


def _build_keys(p: ParsedRelease):
    try:
        from config import resolve_alias
        resolved = resolve_alias(p.clean_name)
        name = resolved.lower().strip()
    except Exception:
        name = (p.clean_name or "").lower().strip()

    res = (p.resolution or "").lower()
    media_id = ""

    if hasattr(p, '_tmdb_id') and p._tmdb_id:
        media_id = f"tmdb:{p._tmdb_id}"
    elif hasattr(p, '_tvdb_id') and p._tvdb_id:
        media_id = f"tvdb:{p._tvdb_id}"

    anchor = media_id if media_id else name

    if p.content_type in (ContentType.EPISODE, ContentType.ANIME_EP):
        if p.date_key:
            ep_id = p.date_key
        elif p.season is not None and p.episode is not None:
            ep_id = f"s{p.season:02d}e{p.episode:02d}"
        elif p.episode is not None:
            p.season = 1
            ep_id = f"s01e{p.episode:02d}"
        elif p.season is not None:
            ep_id = f"s{p.season:02d}"
        elif p.year:
            ep_id = str(p.year)
        else:
            ep_id = ""
        p.family_key = f"{anchor}|{ep_id}"

    elif p.content_type == ContentType.SEASON_PACK:
        s = f"s{p.season:02d}" if p.season is not None else ""
        p.family_key = f"{anchor}|{s}|pack"

    elif p.content_type == ContentType.MOVIE:
        yr = str(p.year) if p.year else ""
        p.family_key = f"{anchor}|{yr}"

    elif p.content_type in (ContentType.GAME, ContentType.GAME_UPDATE):
        p.family_key = f"{name}|game"

    else:
        p.family_key = f"{anchor}|{res}"

    src = (p.source_family or p.source or "").lower()
    svc = (p.service_code or "").lower()

    if p.content_type in (ContentType.GAME, ContentType.GAME_UPDATE):
        gtype = "update" if p.content_type == ContentType.GAME_UPDATE else "game"
        gver = (p.game_version or "").lower()
        p.variant_key = f"{p.family_key}|{gtype}|{gver}"
    else:
        p.variant_key = f"{p.family_key}|{res}|{src}|{svc}"

    grp = (p.group or "").lower()
    cod = (p.codec or "").lower()
    aud = (p.audio or "").lower()
    hdr = (p.hdr or "").lower()
    rev = _get_release_revision(p).lower()

    if p.content_type in (ContentType.GAME, ContentType.GAME_UPDATE):
        p.exact_key = f"{p.variant_key}|{grp}|{rev}"
    else:
        p.exact_key = f"{p.variant_key}|{cod}|{aud}|{hdr}|{grp}|{rev}"

def _parse_huno_title(title: str, match, category: str) -> ParsedRelease:
    name_part = match.group(1).strip()
    year = int(match.group(2))
    tech_part = match.group(3)

    p = ParsedRelease(raw_title=title)
    p.year = year

    se = SEASON_EP_PATTERN.search(name_part)
    if se:
        p.season = int(se.group(1))
        if se.group(2):
            p.episode = int(se.group(2))
            if se.group(3):
                p.episode_end = int(se.group(3))
            p.content_type = ContentType.EPISODE
        else:
            p.content_type = ContentType.SEASON_PACK
        p.clean_name = name_part[:se.start()].strip()
    else:
        p.clean_name = name_part

    p.clean_name = p.clean_name.strip(" -")

    p.resolution = _find_match(tech_part, RESOLUTIONS)
    p.source, p.source_family = _find_source(tech_part)
    p.codec = _find_match(tech_part, CODECS)
    p.audio = _find_audio(tech_part)
    p.hdr = _find_match(tech_part, HDR_TAGS)
    p.group = _extract_group(tech_part) or _extract_group(title)

    if not p.content_type or p.content_type == ContentType.UNKNOWN:
        cat_lower = category.lower()
        if any(kw in cat_lower for kw in ["tv", "show", "episode", "seriale"]):
            p.content_type = ContentType.EPISODE
        else:
            p.content_type = ContentType.MOVIE

    for tag in RELEASE_TAGS:
        if tag.lower() in tech_part.lower():
            p.tags.append(tag)

    p.is_repack = "REPACK" in tech_part.upper()
    p.is_proper = "PROPER" in tech_part.upper()

    return p

def _parse_foreign_episode(title: str, match, category: str) -> ParsedRelease:
    p = ParsedRelease(raw_title=title)
    p.clean_name = match.group("name").strip()
    p.season = 1
    p.episode = int(match.group("episode"))
    p.content_type = ContentType.EPISODE
    p.group = _extract_group(title)
    p.resolution = _find_match(title, RESOLUTIONS)
    p.source, p.source_family = _find_source(title)
    p.codec = _find_match(title, CODECS)
    p.audio = _find_audio(title)
    return p

def _parse_daily(title: str, match, category: str) -> ParsedRelease:
    p = ParsedRelease(raw_title=title)
    p.clean_name = match.group(1).strip()
    year = match.group(2)
    month = match.group(3)
    day = match.group(4)
    p.year = int(year)
    p.date_key = f"{year}-{month}-{day}"
    p.content_type = ContentType.EPISODE
    p.group = _extract_group(title)
    p.resolution = _find_match(title, RESOLUTIONS)
    p.source, p.source_family = _find_source(title)
    p.codec = _find_match(title, CODECS)
    p.audio = _find_audio(title)
    return p


def _parse_daily_dot(title: str, match, category: str) -> ParsedRelease:
    p = ParsedRelease(raw_title=title)
    name = match.group(1).replace(".", " ").strip()
    year = match.group(2)
    month = match.group(3)
    day = match.group(4)
    p.clean_name = name
    p.year = int(year)
    p.date_key = f"{year}-{month}-{day}"
    p.content_type = ContentType.EPISODE
    p.group = _extract_group(title)
    p.resolution = _find_match(title, RESOLUTIONS)
    p.source, p.source_family = _find_source(title)
    p.codec = _find_match(title, CODECS)
    p.audio = _find_audio(title)
    return p


def _try_anime(title: str) -> Optional[ParsedRelease]:
    m = ANIME_SXE_AFTER_DASH_PATTERN.match(title)
    if m:
        p = ParsedRelease(raw_title=title)
        p.group = m.group(1).strip()
        p.clean_name = m.group(2).strip()
        p.season = int(m.group(3))
        p.episode = int(m.group(4))
        p.content_type = ContentType.ANIME_EP
        p.resolution = _find_match(title, RESOLUTIONS)
        return p

    m = ANIME_S_AFTER_NAME_DASH_EP_PATTERN.match(title)
    if m:
        p = ParsedRelease(raw_title=title)
        p.group = m.group(1).strip()
        p.clean_name = m.group(2).strip()
        p.season = int(m.group(3))
        p.episode = int(m.group(4))
        p.content_type = ContentType.ANIME_EP
        p.resolution = _find_match(title, RESOLUTIONS)
        return p

    title = re.sub(r'^\[REQ\]\s*', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'\[(?:BD|DVD|Blu-?Ray)\s*\d+p[^\]]*\]', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'\[(?:Dual[- ]?Audio|Multi[- ]?Audio|Eng(?:lish)?[- ]?Sub(?:bed)?)\]', '', title, flags=re.IGNORECASE).strip()

    m = ANIME_GROUP_PATTERN.match(title)
    if not m:
        return None

    if m.group(1).strip().lower() == "torrent":
        return None

    p = ParsedRelease(raw_title=title)
    p.group = m.group(1)
    p.clean_name = m.group(2).strip().rstrip("-").strip()
    ep_str = m.group(3)
    version = m.group(4)

    if not ep_str:
        trailing_ep = ANIME_TRAILING_EP_PATTERN.search(p.clean_name)
        if trailing_ep:
            p.clean_name = trailing_ep.group("name").strip()
            year_str = trailing_ep.group("year")
            if year_str:
                p.year = int(year_str)
            ep_str = trailing_ep.group("episode")
            if not version:
                version = trailing_ep.group("version")
            tech = trailing_ep.group("tech") or ""
            if not p.resolution:
                p.resolution = _find_match(tech, RESOLUTIONS)

    if ep_str:
        p.episode = int(ep_str)
        if p.season is None:
            p.season = 1
        p.content_type = ContentType.ANIME_EP
    else:
        if (
            SEASON_EP_PATTERN.search(title)
            or re.search(r'\bS\d{1,3}\s*-\s*\d{1,3}\b', title, re.IGNORECASE)
            or re.search(r'\b(?:WEB[-.\s]?DL|WEBRip|x26[45]|H[ .]?26[45])\b', title, re.IGNORECASE)
        ):
            return None
        p.content_type = ContentType.ANIME_BATCH

    if m.group(5):
        p.resolution = m.group(5)

    if version:
        p.tags.append(f"v{version}")
        p.is_repack = True

    if p.group and p.group.lower() in ["erai-raws", "subsplease"]:
        if not p.source:
            p.source = "WEB-DL"
            p.source_family = "WEB-DL"
        if not p.service_code:
            p.service_code = "CR"

    return p


def _parse_sports(title: str, category: str) -> ParsedRelease:
    p = ParsedRelease(raw_title=title, content_type=ContentType.SPORTS)
    p.clean_name = title.split("1080p")[0].split("720p")[0].split("2160p")[0].strip()
    p.group = _extract_group(title)
    p.resolution = _find_match(title, RESOLUTIONS)
    p.source, p.source_family = _find_source(title)
    p.codec = _find_match(title, CODECS)
    return p


def _parse_game(title: str, category: str) -> ParsedRelease:
    p = ParsedRelease(raw_title=title)

    title_lower = title.lower()
    if "update" in title_lower or "patch" in title_lower or "dlc" in title_lower:
        p.content_type = ContentType.GAME_UPDATE
    else:
        p.content_type = ContentType.GAME

    p.group = _extract_group(title)

    raw_version_token = ""
    vm = GAME_VERSION_PATTERN.search(title)
    if vm:
        raw_version_token = vm.group(0)
        p.game_version = re.sub(r'[ _]+', '.', vm.group(1)).strip('.')

    name = title

    if p.group:
        name = re.sub(r'-' + re.escape(p.group) + r'$', '', name)

    if raw_version_token:
        name = name.replace(raw_version_token, "")

    for remove in ["Update", "Patch", "DLC", "Portable", "P2P", "NSW", "PS5", "PS4", "Xbox", "Switch"]:
        name = re.sub(r'\b' + remove + r'\b', '', name, flags=re.IGNORECASE)

    name = re.sub(r'[\[\](){}]', ' ', name)
    name = re.sub(r'[-_.]', ' ', name)
    name = re.sub(r'\bv\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+', ' ', name).strip()

    p.clean_name = name
    return p

def _parse_standard(title: str, category: str) -> ParsedRelease:
    p = ParsedRelease(raw_title=title)

    clean_title = re.sub(r'\((\d{4})\)', r'\1', title)
    clean_title = re.sub(r'^\[REQ\]\s*', '', clean_title, flags=re.IGNORECASE).strip()
    clean_title = re.sub(r'\[(?:BD|DVD|Blu-?Ray)\s*\d+p[^\]]*\]', '', clean_title, flags=re.IGNORECASE).strip()
    clean_title = re.sub(r'\[(?:Dual[- ]?Audio|Multi[- ]?Audio)\]', '', clean_title, flags=re.IGNORECASE).strip()

    p.group = _extract_group(clean_title)
    p.resolution = _find_match(clean_title, RESOLUTIONS)
    p.source, p.source_family = _find_source(clean_title)
    p.codec = _find_match(clean_title, CODECS)
    p.audio = _find_audio(clean_title)
    p.hdr = _find_match(clean_title, HDR_TAGS)

    for tag in RELEASE_TAGS:
        if tag.lower() in clean_title.lower():
            p.tags.append(tag)
    p.is_repack = "REPACK" in clean_title.upper()
    p.is_proper = "PROPER" in clean_title.upper()

    part_match = re.search(r'\bPart\s+(\d+)\b', clean_title, re.IGNORECASE)

    name_part = clean_title
    se = SEASON_EP_PATTERN.search(clean_title)
    ep_only = None

    if se:
        p.season = int(se.group(1))
        if se.group(2):
            p.episode = int(se.group(2))
            if se.group(3):
                p.episode_end = int(se.group(3))
            p.content_type = ContentType.EPISODE
        else:
            p.content_type = ContentType.SEASON_PACK
        name_part = clean_title[:se.start()]

    else:
        cat_lower = category.lower()

        if any(kw in cat_lower for kw in ["episode", "tv", "show", "seriale", "anime"]):
            ep_only = EP_ONLY_PATTERN.search(clean_title)

        if ep_only:
            p.season = 1
            p.episode = int(ep_only.group(1))
            if ep_only.group(2):
                p.episode_end = int(ep_only.group(2))
            p.content_type = ContentType.EPISODE
            name_part = clean_title[:ep_only.start()]

        elif "COMPLETE" in clean_title.upper():
            p.content_type = ContentType.COMPLETE
            name_part = re.split(r'COMPLETE', clean_title, flags=re.IGNORECASE)[0]

        elif "DUOLOGY" in clean_title.upper() or "TRILOGY" in clean_title.upper():
            p.content_type = ContentType.BOXSET
            name_part = re.split(r'(?:DUOLOGY|TRILOGY)', clean_title, flags=re.IGNORECASE)[0]

        else:
            first_marker = len(clean_title)
            for marker in [p.resolution, p.source, p.codec, p.hdr]:
                if marker:
                    idx = clean_title.lower().find(marker.lower())
                    if idx != -1 and idx < first_marker:
                        first_marker = idx
            name_part = clean_title[:first_marker]

            group_lower = (p.group or "").lower()

            if group_lower in GAME_GROUPS:
                p.content_type = ContentType.GAME
            elif any(kw in cat_lower for kw in ["episode", "tv", "show", "seriale"]):
                p.content_type = ContentType.EPISODE
            elif any(kw in cat_lower for kw in ["game", "pc", "nintendo", "ps5", "xbox"]):
                p.content_type = ContentType.GAME
            else:
                p.content_type = ContentType.MOVIE

    if part_match and p.season is None:
        cat_lower = category.lower()
        if any(kw in cat_lower for kw in ["anime", "episode", "tv", "show", "seriale"]):
            p.season = int(part_match.group(1))
            part_idx = part_match.start()
            if part_idx < len(name_part):
                name_part = name_part[:part_idx].strip()
            if p.episode is not None:
                p.content_type = ContentType.EPISODE

    ym = YEAR_PATTERN.search(name_part)
    if ym:
        yr = int(ym.group(1))
        if 1900 <= yr <= 2030:
            p.year = yr
            name_part = name_part[:ym.start(1)].strip()

    if p.group and name_part.startswith(f"[{p.group}]"):
        name_part = name_part[len(p.group) + 2:].strip()

    name_part = re.sub(r'[._]', ' ', name_part)
    name_part = re.sub(r'\s+', ' ', name_part).strip()

    cat_lower = category.lower()
    if "anime" in cat_lower:
        name_part = ANIME_MOVIE_SUFFIX_PATTERN.sub('', name_part).strip()

    aka_match = re.split(r'\s+AKA\s+', name_part, flags=re.IGNORECASE)
    if len(aka_match) > 1:
        name_part = aka_match[0].strip()

    name_part = re.sub(r'^\s*\)', '', name_part).strip()
    if name_part.count("(") != name_part.count(")"):
        name_part = name_part.replace("(", "").replace(")", "").strip()

    name_part = re.sub(r'[\s-]+$', '', name_part).strip()
    p.clean_name = name_part

    cat_lower = category.lower()
    if "anime" in cat_lower and p.content_type == ContentType.MOVIE:
        if p.episode is not None:
            p.content_type = ContentType.ANIME_EP
        elif "COMPLETE" in clean_title.upper():
            p.content_type = ContentType.ANIME_BATCH

    if "boxset" in cat_lower and p.content_type == ContentType.MOVIE:
        p.content_type = ContentType.BOXSET

    if not p.source_family and p.source:
        for label, patterns, family in SOURCE_PATTERNS:
            if p.source.upper() == label.upper():
                p.source_family = family
                break

    if not p.source_family:
        if p.codec and p.codec.lower() in ["x265", "hevc", "av1"] and not p.source:
            p.source_family = "WEBRip"

    return p