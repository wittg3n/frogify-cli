class MP3JuiceError(Exception):
    """Base exception for the package."""


class SearchError(MP3JuiceError):
    """Raised when the search endpoint fails."""


class ResolveError(MP3JuiceError):
    """Raised when an audio download URL cannot be resolved."""

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class DownloadError(MP3JuiceError):
    """Raised when downloading audio bytes fails."""

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}
