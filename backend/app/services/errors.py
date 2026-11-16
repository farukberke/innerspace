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
