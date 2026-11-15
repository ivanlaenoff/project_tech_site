# Регистрация, вход, выход, проверка прав
# -*- coding: utf-8 -*-

from fastapi import Request, HTTPException, Depends
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session
import base64
import hashlib
import hmac
import os

try:
    import bcrypt
    _HAS_BCRYPT = True
except Exception:  # pragma: no cover
    _HAS_BCRYPT = False

import app.models as models
from app.database import SessionLocal


# ======================================================================
# ПАРОЛИ
# ======================================================================
# passlib несовместим с bcrypt>=4.1, поэтому работаем с bcrypt напрямую.
# Для старых хэшей формата passlib ($2b$...) проверка тоже поддерживается.

def _pbkdf2_hash(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return "pbkdf2$200000${}${}".format(
        base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def _pbkdf2_verify(password: str, stored: str) -> bool:
    try:
        _, rounds, salt_b64, digest_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(rounds)
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def hash_password(password: str) -> str:
    password = password or ""
    if _HAS_BCRYPT:
        return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode()
    return _pbkdf2_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    password = password or ""
    if password_hash.startswith("pbkdf2$"):
        return _pbkdf2_verify(password, password_hash)
    if password_hash.startswith("$2") and _HAS_BCRYPT:
        try:
            return bcrypt.checkpw(password.encode("utf-8")[:72],
                                  password_hash.encode("utf-8"))
        except Exception:
            return False
    return False


# ======================================================================
# СЕССИЯ
# ======================================================================

def login_user(request: Request, user_id: int, role: str):
    request.session["user_id"] = user_id
    request.session["role"] = role
    request.session["is_authenticated"] = True


def logout_user(request: Request):
    request.session.clear()


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get("is_authenticated", False))


def get_current_user_role(request: Request):
    return request.session.get("role")


def get_current_user_id(request: Request):
    return request.session.get("user_id")


# ======================================================================
# БД
# ======================================================================

def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ======================================================================
# ТЕКУЩИЙ ПОЛЬЗОВАТЕЛЬ
# ======================================================================

class NotAuthenticated(Exception):
    """Пользователь не вошёл — обрабатывается редиректом на /login."""
    pass


class NotAllowed(Exception):
    """Недостаточно прав."""
    pass


def user_role(user) -> str:
    """Роль в виде строки (в БД может лежать enum или строка)."""
    if user is None:
        return ""
    role = user.role
    return role.value if hasattr(role, "value") else str(role or "")


def display_name(user, db: Session = None) -> str:
    """ФИО пользователя из профиля или email."""
    if user is None:
        return ""
    db = db or SessionLocal()
    close = db is not None
    try:
        if user_role(user) == models.UserRole.STUDENT.value:
            profile = db.query(models.StudentProfile).filter(
                models.StudentProfile.user_id == user.id
            ).first()
            if profile and profile.full_name:
                return profile.full_name
        elif user_role(user) == models.UserRole.TEACHER.value:
            profile = db.query(models.TeacherProfile).filter(
                models.TeacherProfile.user_id == user.id
            ).first()
            if profile and profile.full_name:
                return profile.full_name
        elif user_role(user) == models.UserRole.PARENT.value:
            profile = db.query(models.ParentProfile).filter(
                models.ParentProfile.user_id == user.id
            ).first()
            if profile and profile.full_name:
                return profile.full_name
    finally:
        if close:
            db.close()
    return user.email


def get_current_user(request: Request, db: Session):
    """Пользователь из сессии (с кэшем на время запроса)."""
    cached = getattr(request.state, "current_user", None)
    if cached is not None:
        return cached

    user_id = get_current_user_id(request)
    user = None
    if user_id:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user and not user.is_active:
            user = None

    request.state.current_user = user
    return user


async def require_auth(request: Request, db: Session = Depends(get_db_session)):
    user = get_current_user(request, db)
    if not user:
        raise NotAuthenticated()
    return user


def require_role(*roles):
    roles = [r.value if hasattr(r, "value") else str(r) for r in roles]

    async def checker(request: Request, db: Session = Depends(get_db_session)):
        user = get_current_user(request, db)
        if not user:
            raise NotAuthenticated()
        if user_role(user) not in roles:
            raise NotAllowed()
        return user

    return checker


def student_profile(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user or user_role(user) != models.UserRole.STUDENT.value:
        return None
    return db.query(models.StudentProfile).filter(
        models.StudentProfile.user_id == user.id
    ).first()


def teacher_profile(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user or user_role(user) != models.UserRole.TEACHER.value:
        return None
    return db.query(models.TeacherProfile).filter(
        models.TeacherProfile.user_id == user.id
    ).first()


# ======================================================================
# КОНТЕКСТ ШАБЛОНОВ
# ======================================================================

def add_user_context(request: Request) -> dict:
    """
    Контекст для шаблонов. Полные данные (имя, группа) подтягиваются
    только в том случае, если пользователь вошёл в систему.
    """
    ctx = {
        "is_authenticated": is_authenticated(request),
        "user_role": get_current_user_role(request),
        "user_id": get_current_user_id(request),
        "user_name": request.session.get("full_name", ""),
        "user_group": request.session.get("group_name", ""),
    }
    return ctx


def refresh_session_context(request: Request, user, db: Session):
    """Обновляет кэш имени/группы в сессии после входа."""
    if not user:
        return
    request.session["role"] = user_role(user)
    request.session["full_name"] = display_name(user, db)
    request.session.pop("group_name", None)
    request.session.pop("group_id", None)

    if user_role(user) == models.UserRole.STUDENT.value:
        profile = db.query(models.StudentProfile).filter(
            models.StudentProfile.user_id == user.id
        ).first()
        if profile:
            request.session["group_name"] = profile.group_name or ""
            request.session["group_id"] = profile.group_id
