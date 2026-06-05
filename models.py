from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ContentType(Enum):
    MOVIE = "movie"
    EPISODE = "episode"
    SEASON_PACK = "season_pack"
    COMPLETE = "complete"
    ANIME_EP = "anime_episode"
    ANIME_BATCH = "anime_batch"
    GAME = "game"
    GAME_UPDATE = "game_update"
    SPORTS = "sports"
    BOXSET = "boxset"
    UNKNOWN = "unknown"


class ProfileMode(Enum):
    RACE = "race"
    CONTENT = "content"


class GroupTier(Enum):
    TIER1 = "tier1"
    TIER2 = "tier2"
    TIER3 = "tier3"
    NONE = "none"
    BANNED = "banned"


@dataclass
class ParsedRelease:
    raw_title: str = ""
    clean_name: str = ""
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    episode_end: Optional[int] = None
    resolution: str = ""
    source: str = ""
    source_family: str = ""
    service_code: str = ""
    codec: str = ""
    audio: str = ""
    hdr: str = ""
    group: str = ""
    content_type: ContentType = ContentType.UNKNOWN
    tags: list[str] = field(default_factory=list)
    is_repack: bool = False
    is_proper: bool = False
    is_internal: bool = False
    game_version: str = ""
    family_key: str = ""
    variant_key: str = ""
    exact_key: str = ""
    date_key: str = ""


@dataclass
class TorrentEntry:
    torrent_id: int = 0
    title: str = ""
    category: str = ""
    download_url: str = ""
    page_url: str = ""
    seeders: int = 0
    leechers: int = 0
    pub_date: str = ""
    pub_timestamp: float = 0.0
    feed_source: str = ""
    tracker: str = ""
    size_bytes: int = 0
    info_hash: str = ""
    imdb_id: str = ""
    tmdb_id: int = 0
    uploader: str = ""
    parsed: Optional[ParsedRelease] = None


@dataclass
class MatchResult:
    entry: TorrentEntry = field(default_factory=TorrentEntry)
    profile_name: str = ""
    profile_mode: ProfileMode = ProfileMode.CONTENT
    group_tier: GroupTier = GroupTier.NONE
    matched_keywords: list[str] = field(default_factory=list)
    age_seconds: float = 0.0
    is_dupe: bool = False
    dupe_entries: list[int] = field(default_factory=list)
    velocity: Optional[float] = None
    velocity_label: str = ""
    tmdb_id: Optional[int] = None
    imdb_id: str = ""
    poster_url: str = ""
    tmdb_rating: float = 0.0
    tmdb_overview: str = ""
    family_key: str = ""
    is_new_family: bool = True
    is_new_variant: bool = True
    is_cross_tracker: bool = False
    variants: list[dict] = field(default_factory=list)


@dataclass
class ShowTracker:
    id: int = 0
    show_name: str = ""
    tmdb_id: Optional[int] = None
    latest_season: int = 0
    latest_episode: int = 0
    active: bool = True


@dataclass
class EpisodeRecord:
    show_name: str = ""
    season: int = 0
    episode: int = 0
    torrent_id: int = 0
    group: str = ""
    resolution: str = ""
    found_at: float = 0.0


@dataclass
class GroupPattern:
    group_name: str = ""
    peak_hour_start: int = 0
    peak_hour_end: int = 0
    peak_days: list[str] = field(default_factory=list)
    avg_per_day: float = 0.0
    total_seen: int = 0
    last_upload: float = 0.0


@dataclass
class SeederSnapshot:
    torrent_id: int = 0
    seeders: int = 0
    leechers: int = 0
    checked_at: float = 0.0