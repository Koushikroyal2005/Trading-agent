"""Domain exceptions used across application and infrastructure boundaries."""


class OrderRejectedError(RuntimeError):
    """A broker deterministically rejected an order request."""

    def __init__(self, message: str, status_code: int | None = None, code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
