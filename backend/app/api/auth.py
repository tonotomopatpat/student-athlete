import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import COOKIE_NAME, CurrentUser, DbSession
from app.core.config import get_settings
from app.core.errors import ApiError, conflict
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas import LoginIn, RegisterIn, SettingsIn, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

_FAILURE_WINDOW_SECONDS = 300
_MAX_FAILURES = 8
_failures: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def reset_rate_limits() -> None:
    with _lock:
        _failures.clear()


def _limit_key(request: Request, email: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{client}:{email}"


def _check_not_limited(key: str) -> None:
    now = time.monotonic()
    with _lock:
        attempts = _failures[key]
        while attempts and now - attempts[0] > _FAILURE_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= _MAX_FAILURES:
            raise ApiError(429, "too_many_attempts", "Too many failed sign-in attempts. Try again in a few minutes.")


def _record_failure(key: str) -> None:
    with _lock:
        _failures[key].append(time.monotonic())


def _set_cookie(response: Response, user_id: int) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        create_access_token(user_id),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.token_minutes * 60,
        path="/",
    )


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: RegisterIn, response: Response, db: DbSession) -> User:
    if db.scalar(select(User.id).where(User.email == payload.email)):
        raise conflict("email_taken", "An account with this email already exists.")
    user = User(
        email=payload.email,
        name=payload.name,
        sport=payload.sport or None,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict("email_taken", "An account with this email already exists.")
    _set_cookie(response, user.id)
    return user


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, request: Request, response: Response, db: DbSession) -> User:
    key = _limit_key(request, payload.email)
    _check_not_limited(key)
    user = db.scalar(select(User).where(User.email == payload.email))
    valid = verify_password(payload.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not valid:
        _record_failure(key)
        raise ApiError(401, "invalid_credentials", "Email or password is incorrect.")
    _set_cookie(response, user.id)
    return user


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserOut)
def update_me(payload: SettingsIn, user: CurrentUser, db: DbSession) -> User:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    start = changes.get("study_window_start", user.study_window_start)
    end = changes.get("study_window_end", user.study_window_end)
    if end - start < 60:
        raise ApiError(422, "invalid_window", "Study window must be at least 60 minutes long.")
    for field, value in changes.items():
        setattr(user, field, value)
    db.commit()
    return user
