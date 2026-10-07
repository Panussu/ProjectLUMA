# ข้อผิดพลาดและ Exception สำหรับบริการสร้างภาพ AI Engine (LUMA)
"""Private LUMA AI Engine custom exceptions."""

from __future__ import annotations


class ProviderError(RuntimeError):
    """The configured image provider returned an invalid response."""


class ProviderUnavailable(ProviderError):
    """The configured image provider could not be reached."""


class ApiError(RuntimeError):
    """A stable error response returned by the private LUMA API."""

    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
