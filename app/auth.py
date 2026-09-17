# Регистрация, вход, выход, проверка прав

from passlib.context import CryptContext

from fastapi import (
    Request,
    HTTPException,
    Depends
)

from sqlalchemy.orm import Session

import app.models as models

from app.database import SessionLocal


# ======================
# PASSWORD
# ======================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)



def verify_password(
    password: str,
    password_hash: str
) -> bool:
    return pwd_context.verify(
        password,
        password_hash
    )



# ======================
# SESSION
# ======================

def login_user(
    request: Request,
    user_id: int,
    role: str
):

    request.session["user_id"] = user_id
    request.session["role"] = role
    request.session["is_authenticated"] = True



def logout_user(
    request: Request
):

    request.session.clear()



def is_authenticated(
    request: Request
):

    return request.session.get(
        "is_authenticated",
        False
    )



def get_current_user_role(
    request: Request
):

    return request.session.get(
        "role"
    )



def get_current_user_id(
    request: Request
):

    return request.session.get(
        "user_id"
    )



# ======================
# DATABASE
# ======================

def get_db_session():

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()



# ======================
# CURRENT USER
# ======================

async def get_current_user(
    request: Request,
    db: Session = Depends(get_db_session)
):

    user_id = get_current_user_id(request)

    if not user_id:
        return None


    return (
        db.query(models.User)
        .filter(
            models.User.id == user_id
        )
        .first()
    )



async def require_auth(
    request: Request,
    db: Session = Depends(get_db_session)
):

    user = await get_current_user(
        request,
        db
    )


    if not user:
        raise HTTPException(
            status_code=401,
            detail="Необходимо войти"
        )


    return user



def require_role(
    role
):

    async def checker(
        request: Request,
        db: Session = Depends(get_db_session)
    ):

        user = await require_auth(
            request,
            db
        )


        if user.role != role:

            raise HTTPException(
                status_code=403,
                detail="Нет доступа"
            )


        return user


    return checker



# ======================
# TEMPLATE CONTEXT
# ======================

def add_user_context(
    request: Request
):

    return {

        "is_authenticated":
            is_authenticated(request),

        "user_role":
            get_current_user_role(request),

        "user_id":
            get_current_user_id(request)

    }