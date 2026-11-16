class NotFoundError(Exception):
    """The object does not exist OR is not visible to the actor (callers must not distinguish)."""


class ConflictError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidCredentialsError(Exception):
    pass


class InvalidInvitationError(Exception):
    """Unknown, expired or already used invitation token."""


class PermissionDeniedError(Exception):
    pass


class ValidationFailedError(Exception):
    """A business-rule validation failed (guardrail, empty period, bad edit target)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class CrisisDetectedError(Exception):
    """Crisis language found in user text: no AI content is produced, the fixed crisis response
    is shown instead."""


class RateLimitedError(Exception):
    """A rate limit or usage budget is exhausted; retry after `retry_after` seconds."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("rate limited")
        self.retry_after = max(1, retry_after)
