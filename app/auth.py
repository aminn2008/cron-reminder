import hashlib
import secrets

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuthSession, User

_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS
    ).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS
    ).hex()
    return secrets.compare_digest(candidate, digest)


def create_session(db: Session, user_id: int) -> str:
    token = secrets.token_hex(32)
    db.add(AuthSession(token=token, user_id=user_id))
    db.commit()
    return token


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(401, "لطفاً ابتدا وارد شوید")
    sess = db.query(AuthSession).filter(AuthSession.token == token).first()
    if not sess:
        raise HTTPException(401, "نشست نامعتبر است")
    user = db.get(User, sess.user_id)
    if not user:
        raise HTTPException(401, "کاربر یافت نشد")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "دسترسی ادمین لازم است")
    return user
