"""Expected application errors."""


class SpeechmaticsToolsError(Exception):
    """Base class for user-facing failures."""


class CredentialsError(SpeechmaticsToolsError):
    """The API key could not be loaded safely."""


class ValidationError(SpeechmaticsToolsError):
    """A local argument or file is invalid."""


class ApiError(SpeechmaticsToolsError):
    """Speechmatics returned an error or an invalid response."""
