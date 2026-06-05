import time
import db
from models import TorrentEntry


def compute_velocity(torrent_id: int, current_seeders: int) -> tuple[float | None, str]:
    history = db.get_seeder_history(torrent_id)
    if not history:
        return None, ""

    oldest = history[0]
    delta_time = time.time() - oldest.checked_at
    if delta_time < 10:
        return None, ""

    delta_seeders = current_seeders - oldest.seeders
    velocity = delta_seeders / (delta_time / 60)

    if velocity > 50:
        label = "🔥🔥🔥"
    elif velocity > 20:
        label = "🔥🔥"
    elif velocity > 5:
        label = "🔥"
    elif velocity > 0:
        label = "📈"
    elif velocity < -5:
        label = "📉"
    else:
        label = ""

    return round(velocity, 1), label


def track_seeders(entry: TorrentEntry):
    if entry.torrent_id and entry.seeders >= 0:
        db.add_seeder_snapshot(entry.torrent_id, entry.seeders, entry.leechers)
        db.update_seeders(entry.torrent_id, entry.seeders, entry.leechers)