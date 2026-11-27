from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ApiError
from app.core.security import decode_access_token
from app.models import User

COOKIE_NAME = "access_token"

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(db: DbSession, access_token: Annotated[str | None, Cookie()] = None) -> User:
    user_id = decode_access_token(access_token) if access_token else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise ApiError(401, "unauthenticated", "Please sign in to continue.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
