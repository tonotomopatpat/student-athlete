from fastapi import HTTPException


class ApiError(HTTPException):
    """HTTP error carrying a stable machine code and a user-safe message."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


def not_found(what: str = "Resource") -> ApiError:
    return ApiError(404, "not_found", f"{what} not found.")


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def bad_request(code: str, message: str) -> ApiError:
    return ApiError(400, code, message)
