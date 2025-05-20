"""Custom exceptions for API client interactions."""

class APIClientError(Exception):
    """Base exception for API client errors."""
    def __init__(self, message, status_code=None, error_type=None):
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type

class AuthenticationError(APIClientError):
    """Raised when API authentication fails (e.g., invalid API key, 401, 403)."""
    # __init__ can be inherited if no new params
    pass

class RateLimitError(APIClientError):
    """Raised when the API rate limit is exceeded (e.g., 429)."""
    def __init__(self, message="API rate limit exceeded", status_code=429, retry_after=None):
        self.retry_after = retry_after # Seconds to wait before retrying
        super().__init__(message, status_code=status_code)

class NotFoundError(APIClientError):
    """Raised when a requested resource is not found (e.g., 404)."""
    # __init__ can be inherited if no new params
    pass

class APIRequestError(APIClientError):
    """Raised for general API request errors (e.g., invalid parameters, server errors)."""
    pass

class APIParsingError(APIClientError):
    """Raised when the API response cannot be parsed correctly."""
    def __init__(self, message="Failed to parse API response"):
        super().__init__(message, status_code=None) 