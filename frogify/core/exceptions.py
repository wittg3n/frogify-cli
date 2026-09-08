class FrogifyError(Exception):
    """Base class for expected Frogify failures."""


class SearchError(FrogifyError):
    pass


class NoSafeCandidateError(FrogifyError):
    pass


class DownloadError(FrogifyError):
    pass


class ValidationError(FrogifyError):
    pass


class ConfigurationError(FrogifyError):
    pass
