from .client import MP3JuiceMusicClient
from .exceptions import DownloadError, MP3JuiceError, ResolveError, SearchError
from .models import SearchResult, SongInfo

__all__ = [
    "MP3JuiceMusicClient",
    "SearchResult",
    "SongInfo",
    "MP3JuiceError",
    "SearchError",
    "ResolveError",
    "DownloadError",
]

__version__ = "1.2.0"
