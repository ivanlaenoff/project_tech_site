# -*- coding: utf-8 -*-
import os
import shutil
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware

import app.models as models
from app.auth import (
    add_user_context, display_name, hash_password, is_authenticated,
    login_user, logout_user, refresh_session_context, require_auth,
    require_role, user_role, verify_password,
    NotAuthenticated, NotAllowed,
)
from app.content import PAGES
from app.data import SPECIALTIES
from app.database import Base, SessionLocal, engine
from app.seed import (
    LESSON_TIMES, WEEKDAYS, ensure_seed_data,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
DOCS_DIR = os.path.join(STATIC_DIR, "docs")

os.makedirs(os.path.join(STATIC_DIR, "news"), exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "src"), exist_ok=True)
os.makedirs(DOCS_DIR, exist_ok=True)

app = FastAPI(title="КТТО — Кооперативный техникум Тамбовского облпотребсоюза")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/src", StaticFiles(directory=os.path.join(STATIC_DIR, "src")), name="src")

app.add_middleware(SessionMiddleware,
                   secret_key=os.environ.get("KTTO_SECRET", "ktto-session-secret"))


def _template_context(request: Request) -> dict:
    ctx = add_user_context(request)
    ctx["active_path"] = request.url.path
    return ctx


templates = Jinja2Templates(
    directory=TEMPLATES_DIR,
    context_processors=[_template_context],
)


def _ru_date(value):
    """2026-11-08 → 08.11.2026"""
    if not value:
        return "—"
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return value


def _filesize(value):
    """Размер файла в человекочитаемом виде."""
    try:
        size = int(value)
    except (TypeError, ValueError):
        return ""
    if size < 1024:
        return f"{size} Б"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} КБ"
    return f"{size / (1024 * 1024):.1f} МБ"


templates.env.filters["ru_date"] = _ru_date
templates.env.filters["filesize"] = _filesize


Base.metadata.create_all(bind=engine)
ensure_seed_data()


# ========== ОБРАБОТЧИКИ ОШИБОК АВТОРИЗАЦИИ ==========
@app.exception_handler(NotAuthenticated)
async def not_authenticated_handler(request: Request, exc: NotAuthenticated):
    return RedirectResponse(url=f"/login?next={request.url.path}", status_code=303)


@app.exception_handler(NotAllowed)
async def not_allowed_handler(request: Request, exc: NotAllowed):
    return templates.TemplateResponse(request, "error.html", {
        "request": request,
        "code": 403,
        "title": "Нет доступа",
        "message": "Этот раздел доступен только пользователям с подходящей ролью.",
    }, status_code=403)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _safe_next(next_url: Optional[str]) -> str:
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return "/"


def _short_name(profile) -> str:
    """Иванова Мария Ивановна → Иванова М. И."""
    if not profile or not profile.last_name:
        return ""
    first = (profile.first_name or "")[:1]
    middle = ""
    return f"{profile.last_name} {first}."


# ========== ГЛАВНАЯ ==========
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    news_items = db.query(models.News).order_by(models.News.id.desc()).limit(6).all()

    gallery = [img.image_url for img in
               db.query(models.NewsImage).order_by(models.NewsImage.id.desc()).limit(8).all()
               if img.image_url]
    videos = [item.video_url for item in
              db.query(models.News).filter(models.News.video_url.isnot(None))
              .order_by(models.News.id.desc()).limit(3).all()
              if item.video_url]

    return templates.TemplateResponse(request, "index.html", {
        "request": request,
        "news": news_items,
        "gallery": gallery,
        "videos": videos,
        **add_user_context(request),
    })


# ========== НОВОСТИ ==========
@app.get("/news/{news_id}", response_class=HTMLResponse)
async def read_news_item(request: Request, news_id: int, db: Session = Depends(get_db)):
    news_item = db.query(models.News).filter(models.News.id == news_id).first()
    if not news_item:
        raise HTTPException(status_code=404, detail="Новость не найдена")

    images = db.query(models.NewsImage).filter(models.NewsImage.news_id == news_id).all()
    documents = db.query(models.NewsDocument).filter(models.NewsDocument.news_id == news_id).all()
    other_news = (db.query(models.News).filter(models.News.id != news_id)
                  .order_by(models.News.id.desc()).limit(5).all())

    return templates.TemplateResponse(request, "news.html", {
        "request": request,
        "post": news_item,
        "images": images,
        "documents": documents,
        "other_news": other_news,
        **add_user_context(request),
    })


@app.get("/all_news", response_class=HTMLResponse)
def get_all_news(
    request: Request,
    page: int = 1,
    date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    per_page = 6
    query = db.query(models.News)

    if date:
        parts = date.split("-")
        date_dotted = f"{parts[2]}.{parts[1]}.{parts[0]}" if len(parts) == 3 else ""
        query = query.filter(
            or_(
                cast(models.News.date, String).like(f"%{date}%"),
                cast(models.News.date, String).like(f"%{date_dotted}%"),
            )
        )

    total_news = query.count()
    total_pages = (total_news + per_page - 1) // per_page
    news = query.offset((page - 1) * per_page).limit(per_page).all()

    return templates.TemplateResponse(request, "all_news.html", {
        "request": request,
        "news": news,
        "current_page": page,
        "total_pages": max(total_pages, 1),
        "selected_date": date,
        **add_user_context(request),
    })


@app.get("/api/news-dates")
def get_news_dates(db: Session = Depends(get_db)):
    news_items = db.query(models.News).all()
    dates = set()
    for item in news_items:
        if item.date:
            if hasattr(item.date, "strftime"):
                dates.add(item.date.strftime("%Y-%m-%d"))
            else:
                date_str = str(item.date).strip()
                parts = date_str.split(".")
                if len(parts) == 3:
                    dates.add(f"{parts[2]}-{parts[1]}-{parts[0]}")
                else:
                    dates.add(date_str)
    return {"dates": list(dates)}


# ========== СТАТИЧЕСКИЕ И ИНФОРМАЦИОННЫЕ СТРАНИЦЫ ==========
@app.get("/about", response_class=HTMLResponse)
async def get_about_page(request: Request):
    return templates.TemplateResponse(request, "about.html", {
        "request": request, **add_user_context(request)})


@app.get("/admission", response_class=HTMLResponse)
async def get_admission_page(request: Request):
    return templates.TemplateResponse(request, "admission.html", {
        "request": request, **add_user_context(request)})


@app.get("/students", response_class=HTMLResponse)
async def get_students_page(request: Request):
    return templates.TemplateResponse(request, "students.html", {
        "request": request, **add_user_context(request)})


@app.get("/info", response_class=HTMLResponse)
async def get_info_page(request: Request):
    return templates.TemplateResponse(request, "info.html", {
        "request": request, **add_user_context(request)})


@app.get("/contacts", response_class=HTMLResponse)
async def get_contacts_page(request: Request):
    return templates.TemplateResponse(request, "contacts.html", {
        "request": request, **add_user_context(request)})


@app.post("/contacts", response_class=HTMLResponse)
async def post_contacts_page(
    request: Request,
    name: str = Form(...),
    contact: str = Form(...),
    message: str = Form(...),
    topic: str = Form(None),
    db: Session = Depends(get_db),
):
    db.add(models.FeedbackMessage(
        name=name.strip()[:120],
        contact=contact.strip()[:120],
        topic=(topic or "Другое")[:120],
        message=message.strip()[:4000],
    ))
    db.commit()
    return templates.TemplateResponse(request, "contacts.html", {
        "request": request,
        "success": True,
        **add_user_context(request),
    })


@app.get("/apply", response_class=HTMLResponse)
async def get_apply_page(request: Request):
    return templates.TemplateResponse(request, "apply.html", {
        "request": request, **add_user_context(request)})


@app.post("/apply")
async def post_application(
    request: Request,
    fio: str = Form(...),
    phone: str = Form(...),
    db: Session = Depends(get_db),
):
    db.add(models.Application(fio=fio, phone=phone))
    db.commit()
    return templates.TemplateResponse(request, "apply.html", {
        "request": request,
        "success": True,
        **add_user_context(request),
    })


@app.get("/specialties", response_class=HTMLResponse)
async def specialties_page(request: Request, item: str = None):
    current = SPECIALTIES[0]
    if item:
        for s in SPECIALTIES:
            if s["id"] == item:
                current = s
    return templates.TemplateResponse(request, "specialties.html", {
        "request": request,
        "current": current,
        "specialties": SPECIALTIES,
        **add_user_context(request),
    })


# ========== ДОКУМЕНТЫ ==========
@app.get("/documents", response_class=HTMLResponse)
async def documents_page(request: Request, category: Optional[str] = None,
                         db: Session = Depends(get_db)):
    query = db.query(models.DocumentFile)
    if category:
        query = query.filter(models.DocumentFile.category == category)
    docs = query.order_by(models.DocumentFile.order, models.DocumentFile.id).all()

    categories = [row[0] for row in
                  db.query(models.DocumentFile.category).distinct().all() if row[0]]

    grouped = {}
    for doc in docs:
        grouped.setdefault(doc.category or "Общие", []).append(doc)

    return templates.TemplateResponse(request, "documents.html", {
        "request": request,
        "documents": docs,
        "grouped": grouped,
        "categories": categories,
        "selected_category": category,
        **add_user_context(request),
    })


# ========== ГАЛЕРЕЯ ==========
@app.get("/gallery", response_class=HTMLResponse)
async def gallery_page(request: Request, db: Session = Depends(get_db)):
    images = [img for img in db.query(models.NewsImage).order_by(
        models.NewsImage.id.desc()).all() if img.image_url]
    covers = [item for item in db.query(models.News).filter(
        models.News.image_url.isnot(None)).order_by(models.News.id.desc()).all()]
    videos = [item for item in db.query(models.News).filter(
        models.News.video_url.isnot(None)).order_by(models.News.id.desc()).all()]

    news_map = {n.id: n for n in db.query(models.News).all()}

    return templates.TemplateResponse(request, "gallery.html", {
        "request": request,
        "images": images,
        "covers": covers,
        "videos": videos,
        "news_map": news_map,
        **add_user_context(request),
    })


# ========== ВНУТРЕННИЕ СТРАНИЦЫ (контент из app/content.py) ==========
def _make_page_view(slug: str, page: dict):
    async def view(request: Request):
        related = [
            {"slug": other_slug, "title": other["title"], "menu_title": other.get("menu_title")}
            for other_slug, other in PAGES.items()
            if other["parent"]["href"] == page["parent"]["href"] and other_slug != slug
        ]
        return templates.TemplateResponse(request, "info_page.html", {
            "request": request,
            "page": page,
            "related": related,
            **add_user_context(request),
        })
    return view


for _slug, _page in PAGES.items():
    app.add_api_route(
        f"/{_slug}",
        _make_page_view(_slug, _page),
        response_class=HTMLResponse,
        name=f"info_page_{_slug.replace('/', '_')}",
        methods=["GET"],
    )


# ========== ВХОД / РЕГИСТРАЦИЯ ==========
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    if is_authenticated(request):
        return RedirectResponse(url=_safe_next(next), status_code=303)
    return templates.TemplateResponse(request, "login.html", {
        "request": request,
        "next": next or "",
        **add_user_context(request),
    })


@app.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    user = db.query(models.User).filter(func.lower(models.User.email) == email).first()

    def error(text):
        return templates.TemplateResponse(request, "login.html", {
            "request": request,
            "error": text,
            "email": email,
            "next": next or "",
            **add_user_context(request),
        }, status_code=400)

    if not user:
        return error("Пользователь с таким email не найден")
    if not verify_password(password, user.password_hash):
        return error("Неверный пароль")
    if not user.is_active:
        return error("Аккаунт заблокирован. Обратитесь в учебную часть")

    login_user(request, user.id, user_role(user))
    refresh_session_context(request, user, db)

    if user_role(user) == models.UserRole.TEACHER.value:
        return RedirectResponse(url=_safe_next(next) if next else "/teacher", status_code=303)
    if user_role(user) == models.UserRole.ADMIN.value:
        return RedirectResponse(url=_safe_next(next) if next else "/admin", status_code=303)
    return RedirectResponse(url=_safe_next(next), status_code=303)


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: Session = Depends(get_db)):
    groups = db.query(models.Group).order_by(models.Group.name).all()
    return templates.TemplateResponse(request, "register.html", {
        "request": request,
        "groups": groups,
        **add_user_context(request),
    })


@app.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone: str = Form(None),
    group_name: str = Form(None),
    role: str = Form("student"),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    groups = db.query(models.Group).order_by(models.Group.name).all()

    def error(text):
        return templates.TemplateResponse(request, "register.html", {
            "request": request,
            "error": text,
            "groups": groups,
            "form": {
                "email": email, "first_name": first_name, "last_name": last_name,
                "phone": phone, "group_name": group_name, "role": role,
            },
            **add_user_context(request),
        }, status_code=400)

    if role not in ("student", "parent"):
        return error("Самостоятельная регистрация доступна только студентам и родителям")
    if password != confirm_password:
        return error("Пароли не совпадают")
    if len(password) < 6:
        return error("Пароль должен содержать не менее 6 символов")
    if db.query(models.User).filter(func.lower(models.User.email) == email).first():
        return error("Пользователь с таким email уже зарегистрирован")
    if role == "student" and not group_name:
        return error("Выберите учебную группу")

    user = models.User(
        email=email,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(user)
    db.flush()

    if role == "student":
        group = db.query(models.Group).filter(models.Group.name == group_name).first()
        db.add(models.StudentProfile(
            user_id=user.id,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            phone=phone,
            group_name=group_name,
            group_id=group.id if group else None,
        ))
    else:
        db.add(models.ParentProfile(
            user_id=user.id,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            phone=phone,
        ))

    db.commit()
    db.refresh(user)

    login_user(request, user.id, user_role(user))
    refresh_session_context(request, user, db)
    return RedirectResponse(url="/diary", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    logout_user(request)
    return RedirectResponse(url="/", status_code=303)


# Служебный вход для локальной проверки интерфейса (только при KTTO_DEV_LOGIN=1)
if os.environ.get("KTTO_DEV_LOGIN") == "1":
    @app.get("/__dev_login")
    async def dev_login(request: Request, email: str, next: str = "/", db: Session = Depends(get_db)):
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            raise HTTPException(status_code=404)
        login_user(request, user.id, user_role(user))
        refresh_session_context(request, user, db)
        return RedirectResponse(url=_safe_next(next), status_code=303)


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    user: models.User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    role = user_role(user)
    profile = None
    if role == models.UserRole.STUDENT.value:
        profile = db.query(models.StudentProfile).filter(
            models.StudentProfile.user_id == user.id).first()
    elif role == models.UserRole.TEACHER.value:
        profile = db.query(models.TeacherProfile).filter(
            models.TeacherProfile.user_id == user.id).first()
    elif role == models.UserRole.PARENT.value:
        profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == user.id).first()

    return templates.TemplateResponse(request, "profile.html", {
        "request": request,
        "user": user,
        "profile": profile,
        "role": role,
        **add_user_context(request),
    })


@app.post("/profile/password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: models.User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    role = user_role(user)
    profile = None
    if role == models.UserRole.STUDENT.value:
        profile = db.query(models.StudentProfile).filter(
            models.StudentProfile.user_id == user.id).first()
    elif role == models.UserRole.TEACHER.value:
        profile = db.query(models.TeacherProfile).filter(
            models.TeacherProfile.user_id == user.id).first()

    def render(error=None, success=None):
        return templates.TemplateResponse(request, "profile.html", {
            "request": request, "user": user, "profile": profile, "role": role,
            "error": error, "success": success, **add_user_context(request),
        }, status_code=400 if error else 200)

    if not verify_password(current_password, user.password_hash):
        return render(error="Текущий пароль указан неверно")
    if new_password != confirm_password:
        return render(error="Новые пароли не совпадают")
    if len(new_password) < 6:
        return render(error="Пароль должен содержать не менее 6 символов")

    user.password_hash = hash_password(new_password)
    db.commit()
    return render(success="Пароль обновлён")


# ========== РАСПИСАНИЕ ==========
def _schedule_grid(rows):
    grid = {}
    for row in rows:
        grid.setdefault(row.weekday, {})[row.lesson_no] = row
    return grid


@app.get("/schedule", response_class=HTMLResponse)
async def schedule_page(
    request: Request,
    group: str = None,
    db: Session = Depends(get_db),
):
    user = None
    user_id = request.session.get("user_id")
    if user_id:
        user = db.query(models.User).filter(models.User.id == user_id).first()

    role = user_role(user) if user else ""
    groups = db.query(models.Group).order_by(models.Group.name).all()

    profile = None
    if role == models.UserRole.STUDENT.value:
        profile = db.query(models.StudentProfile).filter(
            models.StudentProfile.user_id == user.id).first()
        group = (profile.group_name if profile else None) or group

    if not group and groups:
        group = groups[0].name

    current_group = db.query(models.Group).filter(models.Group.name == group).first()
    rows = []
    if current_group:
        rows = (db.query(models.Schedule)
                .filter(models.Schedule.group_id == current_group.id)
                .order_by(models.Schedule.weekday, models.Schedule.lesson_no).all())

    grid = _schedule_grid(rows)

    today = date.today().isoweekday()
    today_weekday = today if 1 <= today <= 6 else None

    return templates.TemplateResponse(request, "schedule.html", {
        "request": request,
        "groups": groups,
        "current_group": current_group,
        "group_name": group,
        "grid": grid,
        "weekdays": WEEKDAYS,
        "lesson_times": LESSON_TIMES,
        "today_weekday": today_weekday,
        "is_student_view": role == models.UserRole.STUDENT.value,
        **add_user_context(request),
    })


# ========== ДНЕВНИК ==========
@app.get("/diary", response_class=HTMLResponse)
async def diary_page(
    request: Request,
    user: models.User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    role = user_role(user)
    if role == models.UserRole.TEACHER.value:
        return RedirectResponse(url="/teacher", status_code=303)
    if role == models.UserRole.ADMIN.value:
        return RedirectResponse(url="/admin", status_code=303)

    profile = db.query(models.StudentProfile).filter(
        models.StudentProfile.user_id == user.id).first()

    grades = []
    by_subject = {}
    average = None
    if profile:
        grades = (db.query(models.Grade)
                  .filter(models.Grade.user_id == user.id)
                  .order_by(models.Grade.date.desc(), models.Grade.id.desc()).all())
        for g in grades:
            bucket = by_subject.setdefault(g.subject, {"marks": [], "avg": None})
            bucket["marks"].append(g.mark)
        for subject, bucket in by_subject.items():
            bucket["avg"] = round(sum(bucket["marks"]) / len(bucket["marks"]), 2)
        if grades:
            average = round(sum(g.mark for g in grades) / len(grades), 2)

    homework = []
    group = None
    if profile and profile.group_id:
        group = db.query(models.Group).filter(models.Group.id == profile.group_id).first()
        homework = (db.query(models.Homework)
                    .filter(models.Homework.group_id == profile.group_id)
                    .order_by(models.Homework.due_date).all())

    today_lessons = []
    if group:
        weekday = date.today().isoweekday()
        if 1 <= weekday <= 6:
            today_lessons = (db.query(models.Schedule)
                             .filter(models.Schedule.group_id == group.id,
                                     models.Schedule.weekday == weekday)
                             .order_by(models.Schedule.lesson_no).all())

    return templates.TemplateResponse(request, "diary.html", {
        "request": request,
        "user": user,
        "profile": profile,
        "group": group,
        "grades": grades,
        "by_subject": by_subject,
        "average": average,
        "homework": homework,
        "today_lessons": today_lessons,
        "lesson_times": LESSON_TIMES,
        **add_user_context(request),
    })


# ========== КАБИНЕТ ПРЕПОДАВАТЕЛЯ ==========
@app.get("/teacher", response_class=HTMLResponse)
async def teacher_dashboard(
    request: Request,
    user: models.User = Depends(require_role("teacher", "admin")),
    db: Session = Depends(get_db),
):
    profile = db.query(models.TeacherProfile).filter(
        models.TeacherProfile.user_id == user.id).first()
    short = _short_name(profile)

    groups = db.query(models.Group).order_by(models.Group.name).all()
    weekday = date.today().isoweekday()
    today_lessons = []
    if 1 <= weekday <= 6:
        today_lessons = (db.query(models.Schedule)
                         .filter(models.Schedule.weekday == weekday)
                         .order_by(models.Schedule.lesson_no).all())

    last_name = (profile.last_name or "") if profile else ""
    my_lessons = [l for l in today_lessons
                  if last_name and (l.teacher_name or "").startswith(last_name)]

    students = (db.query(models.StudentProfile)
                .order_by(models.StudentProfile.group_name, models.StudentProfile.last_name)
                .all())

    groups_count = {g.name: sum(1 for s in students if s.group_name == g.name) for g in groups}

    return templates.TemplateResponse(request, "teacher.html", {
        "request": request,
        "profile": profile,
        "short_name": short,
        "groups": groups,
        "groups_count": groups_count,
        "today_lessons": today_lessons,
        "my_lessons": my_lessons,
        "students": students,
        "weekday_name": WEEKDAYS.get(weekday, "Воскресенье"),
        "lesson_times": LESSON_TIMES,
        **add_user_context(request),
    })


@app.get("/teacher/journal", response_class=HTMLResponse)
async def teacher_journal(
    request: Request,
    group: str = None,
    user: models.User = Depends(require_role("teacher", "admin")),
    db: Session = Depends(get_db),
):
    groups = db.query(models.Group).order_by(models.Group.name).all()
    if not group and groups:
        group = groups[0].name
    current_group = db.query(models.Group).filter(models.Group.name == group).first()

    students, student_rows, recent_grades = [], [], []
    if current_group:
        students = (db.query(models.StudentProfile)
                    .filter(models.StudentProfile.group_name == current_group.name)
                    .order_by(models.StudentProfile.last_name).all())
        for s in students:
            grades = (db.query(models.Grade)
                      .filter(models.Grade.user_id == s.user_id)
                      .order_by(models.Grade.date.desc()).all())
            avg = round(sum(g.mark for g in grades) / len(grades), 2) if grades else None
            student_rows.append({
                "profile": s,
                "avg": avg,
                "count": len(grades),
                "last": grades[0] if grades else None,
            })
        ids = [s.user_id for s in students]
        if ids:
            recent_grades = (db.query(models.Grade)
                             .filter(models.Grade.user_id.in_(ids))
                             .order_by(models.Grade.date.desc(), models.Grade.id.desc())
                             .limit(15).all())

    return templates.TemplateResponse(request, "teacher_journal.html", {
        "request": request,
        "groups": groups,
        "current_group": current_group,
        "students": students,
        "student_rows": student_rows,
        "recent_grades": recent_grades,
        "today": date.today().strftime("%Y-%m-%d"),
        **add_user_context(request),
    })


@app.post("/teacher/grade")
async def teacher_add_grade(
    request: Request,
    student_id: int = Form(...),
    subject: str = Form(...),
    mark: int = Form(...),
    grade_date: str = Form(None),
    comment: str = Form(None),
    group: str = Form(None),
    user: models.User = Depends(require_role("teacher", "admin")),
    db: Session = Depends(get_db),
):
    profile = db.query(models.StudentProfile).filter(
        models.StudentProfile.user_id == student_id).first()
    teacher = db.query(models.TeacherProfile).filter(
        models.TeacherProfile.user_id == user.id).first()

    if profile and 1 <= int(mark) <= 5:
        db.add(models.Grade(
            user_id=student_id,
            subject=subject.strip()[:120],
            mark=int(mark),
            date=grade_date or date.today().strftime("%Y-%m-%d"),
            teacher_name=_short_name(teacher),
            comment=(comment or "").strip()[:300] or None,
        ))
        db.commit()

    target = f"/teacher/journal?group={group}" if group else "/teacher/journal"
    return RedirectResponse(url=target, status_code=303)


@app.post("/teacher/grade/delete")
async def teacher_delete_grade(
    grade_id: int = Form(...),
    group: str = Form(None),
    user: models.User = Depends(require_role("teacher", "admin")),
    db: Session = Depends(get_db),
):
    grade = db.query(models.Grade).filter(models.Grade.id == grade_id).first()
    if grade:
        db.delete(grade)
        db.commit()
    return RedirectResponse(url=f"/teacher/journal?group={group}" if group else "/teacher/journal",
                            status_code=303)


@app.get("/teacher/schedule", response_class=HTMLResponse)
async def teacher_schedule(
    request: Request,
    group: str = None,
    user: models.User = Depends(require_role("teacher", "admin")),
    db: Session = Depends(get_db),
):
    groups = db.query(models.Group).order_by(models.Group.name).all()
    if not group and groups:
        group = groups[0].name
    current_group = db.query(models.Group).filter(models.Group.name == group).first()

    rows = []
    if current_group:
        rows = (db.query(models.Schedule)
                .filter(models.Schedule.group_id == current_group.id)
                .order_by(models.Schedule.weekday, models.Schedule.lesson_no).all())

    return templates.TemplateResponse(request, "teacher_schedule.html", {
        "request": request,
        "groups": groups,
        "current_group": current_group,
        "group_name": group,
        "rows": rows,
        "grid": _schedule_grid(rows),
        "weekdays": WEEKDAYS,
        "lesson_times": LESSON_TIMES,
        "lesson_types": ["Лекция", "Практика", "Лабораторная"],
        **add_user_context(request),
    })


@app.post("/teacher/schedule/save")
async def teacher_schedule_save(
    group: str = Form(...),
    weekday: int = Form(...),
    lesson_no: int = Form(...),
    subject: str = Form(...),
    teacher_name: str = Form(None),
    room: str = Form(None),
    lesson_type: str = Form("Практика"),
    user: models.User = Depends(require_role("teacher", "admin")),
    db: Session = Depends(get_db),
):
    current_group = db.query(models.Group).filter(models.Group.name == group).first()
    if current_group:
        existing = (db.query(models.Schedule)
                    .filter(models.Schedule.group_id == current_group.id,
                            models.Schedule.weekday == weekday,
                            models.Schedule.lesson_no == lesson_no).first())
        if existing:
            existing.subject = subject.strip()
            existing.teacher_name = teacher_name
            existing.room = room
            existing.lesson_type = lesson_type
        else:
            db.add(models.Schedule(
                group_id=current_group.id, weekday=weekday, lesson_no=lesson_no,
                subject=subject.strip(), teacher_name=teacher_name, room=room,
                lesson_type=lesson_type,
            ))
        db.commit()
    return RedirectResponse(url=f"/teacher/schedule?group={group}", status_code=303)


@app.post("/teacher/schedule/delete")
async def teacher_schedule_delete(
    lesson_id: int = Form(...),
    group: str = Form(None),
    user: models.User = Depends(require_role("teacher", "admin")),
    db: Session = Depends(get_db),
):
    row = db.query(models.Schedule).filter(models.Schedule.id == lesson_id).first()
    if row:
        db.delete(row)
        db.commit()
    return RedirectResponse(url=f"/teacher/schedule?group={group}" if group else "/teacher/schedule",
                            status_code=303)


@app.post("/teacher/homework")
async def teacher_add_homework(
    group: str = Form(...),
    subject: str = Form(...),
    task: str = Form(...),
    due_date: str = Form(None),
    user: models.User = Depends(require_role("teacher", "admin")),
    db: Session = Depends(get_db),
):
    current_group = db.query(models.Group).filter(models.Group.name == group).first()
    teacher = db.query(models.TeacherProfile).filter(
        models.TeacherProfile.user_id == user.id).first()
    if current_group:
        db.add(models.Homework(
            group_id=current_group.id,
            subject=subject.strip()[:120],
            task=task.strip()[:1000],
            due_date=due_date or None,
            teacher_name=_short_name(teacher),
        ))
        db.commit()
    return RedirectResponse(url=f"/teacher/journal?group={group}", status_code=303)


# ========== АДМИНКА ==========
def _save_upload(file, subdir="news", prefix="file"):
    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    filename = f"{prefix}_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(STATIC_DIR, subdir, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return filename, filepath


class AdminAuth(AuthenticationBackend):
    """Авторизация в /admin: администраторы и преподаватели."""

    def __init__(self):
        # Отдельная cookie для админки, чтобы не конфликтовать с основной сессией
        self.middlewares = [
            Middleware(SessionMiddleware,
                       secret_key=os.environ.get("KTTO_ADMIN_SECRET", "ktto-admin-secret"),
                       session_cookie="admin_session"),
        ]
        self.login_path = "/admin/login"

    async def login(self, request: Request) -> bool:
        form = await request.form()
        email = (form.get("username") or "").strip().lower()
        password = form.get("password") or ""

        db = SessionLocal()
        try:
            user = db.query(models.User).filter(func.lower(models.User.email) == email).first()
            ok = bool(user) and bool(user.is_active) and verify_password(
                password, user.password_hash) and user_role(user) in (
                models.UserRole.ADMIN.value, models.UserRole.TEACHER.value)
            if ok:
                request.session.update({
                    "admin_authenticated": True,
                    "admin_email": user.email,
                    "admin_name": display_name(user, db),
                })
            return ok
        finally:
            db.close()

    async def logout(self, request: Request):
        request.session.clear()
        return True

    async def authenticate(self, request: Request):
        if not request.session.get("admin_authenticated"):
            try:
                return RedirectResponse(request.url_for("admin:login"), status_code=302)
            except Exception:
                return RedirectResponse("/admin/login", status_code=302)
        return True


class NewsAdmin(ModelView, model=models.News):
    name = "Новость"
    name_plural = "Новости"
    icon = "fa-solid fa-newspaper"
    column_list = [models.News.id, models.News.title, models.News.date]
    column_searchable_list = [models.News.title, models.News.description]
    form_columns = ["title", "description", "date"]

    async def scaffold_form(self, *args, **kwargs):
        from wtforms import FileField, StringField
        form_class = await super().scaffold_form(*args, **kwargs)
        form_class.image_file = FileField("Загрузить картинку (обложка)")
        form_class.video_upload = FileField("Загрузить видео файл")
        form_class.gallery_files = FileField(
            "Дополнительные фото (можно выбрать несколько)",
            render_kw={"multiple": True},
        )
        form_class.document_files = FileField(
            "Документы", render_kw={"multiple": True})
        form_class.video_order = StringField(
            "Порядковый номер видео", default="0",
            render_kw={"style": "width: 100%; padding: 8px;"})
        return form_class

    async def on_model_change(self, data, model, is_created, request):
        form_data = await request.form()

        file = form_data.get("image_file")
        if file and hasattr(file, "filename") and file.filename:
            filename, _ = _save_upload(file, "news", "news")
            model.image_url = f"/static/news/{filename}"

        video_file = form_data.get("video_upload")
        if video_file and hasattr(video_file, "filename") and video_file.filename:
            filename, _ = _save_upload(video_file, os.path.join("news", "videos"), "video")
            model.video_url = f"/static/news/videos/{filename}"

        if model.date:
            try:
                d = datetime.strptime(model.date, "%Y-%m-%d")
                model.date = d.strftime("%d %B %Y")
            except Exception:
                pass

        raw_order = form_data.get("video_order")
        model.video_order = int(raw_order) if raw_order and raw_order.isdigit() else 0

        self._pending_gallery = form_data.getlist("gallery_files")
        self._pending_documents = form_data.getlist("document_files")

    async def after_model_change(self, data, model, is_created, request):
        db = SessionLocal()
        try:
            for file in getattr(self, "_pending_gallery", []):
                if file and hasattr(file, "filename") and file.filename:
                    filename, _ = _save_upload(file, "news", "gallery")
                    db.add(models.NewsImage(
                        news_id=model.id, image_url=f"/static/news/{filename}"))

            for file in getattr(self, "_pending_documents", []):
                if file and hasattr(file, "filename") and file.filename:
                    ext = file.filename.split(".")[-1]
                    filename, _ = _save_upload(file, "news", "doc")
                    db.add(models.NewsDocument(
                        news_id=model.id,
                        file_name=file.filename,
                        file_url=f"/static/news/{filename}",
                    ))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
            self._pending_gallery = []
            self._pending_documents = []


class DocumentAdmin(ModelView, model=models.DocumentFile):
    name = "Документ"
    name_plural = "Документы"
    icon = "fa-solid fa-file-lines"
    column_list = [models.DocumentFile.id, models.DocumentFile.title,
                   models.DocumentFile.category, models.DocumentFile.file_url]
    column_searchable_list = [models.DocumentFile.title, models.DocumentFile.category]
    column_labels = {
        "title": "Название", "category": "Раздел", "file_url": "Файл",
        "description": "Описание", "order": "Порядок",
    }
    form_columns = ["title", "category", "description", "order"]

    async def scaffold_form(self, *args, **kwargs):
        from wtforms import FileField
        form_class = await super().scaffold_form(*args, **kwargs)
        form_class.file_upload = FileField("Файл документа (PDF, DOCX)")
        return form_class

    async def on_model_change(self, data, model, is_created, request):
        form_data = await request.form()
        file = form_data.get("file_upload")
        if file and hasattr(file, "filename") and file.filename:
            filename, filepath = _save_upload(file, "docs", "doc")
            model.file_name = file.filename
            model.file_url = f"/static/docs/{filename}"
            try:
                model.file_size = os.path.getsize(filepath)
            except OSError:
                model.file_size = None


class ScheduleAdmin(ModelView, model=models.Schedule):
    name = "Пара"
    name_plural = "Расписание"
    icon = "fa-solid fa-calendar-days"
    column_list = [models.Schedule.id, models.Schedule.group, models.Schedule.weekday,
                   models.Schedule.lesson_no, models.Schedule.subject]
    column_sortable_list = [models.Schedule.weekday, models.Schedule.lesson_no]
    form_columns = ["group", "weekday", "lesson_no", "subject", "teacher_name",
                    "room", "lesson_type"]
    column_labels = {
        "group": "Группа", "weekday": "День (1–6)", "lesson_no": "Пара (1–5)",
        "subject": "Предмет", "teacher_name": "Преподаватель",
        "room": "Кабинет", "lesson_type": "Тип занятия",
    }


class GroupAdmin(ModelView, model=models.Group):
    name = "Группа"
    name_plural = "Группы"
    icon = "fa-solid fa-users"
    column_list = [models.Group.id, models.Group.name, models.Group.specialty_id,
                   models.Group.course, models.Group.curator]
    form_columns = ["name", "specialty_id", "course", "curator", "students_count"]


class UserAdmin(ModelView, model=models.User):
    name = "Пользователь"
    name_plural = "Пользователи и учителя"
    icon = "fa-solid fa-user"
    column_list = [models.User.id, models.User.email, models.User.role,
                   models.User.is_active]
    column_labels = {
        "id": "ID", "email": "Email", "role": "Роль", "is_active": "Активен",
    }
    column_searchable_list = [models.User.email]
    form_columns = ["email", "role", "is_active"]
    form_args = {}
    column_default_sort = ("id", True)

    async def scaffold_form(self, *args, **kwargs):
        from wtforms import PasswordField
        form_class = await super().scaffold_form(*args, **kwargs)
        form_class.new_password = PasswordField(
            "Новый пароль (оставьте пустым, чтобы не менять)")
        return form_class

    async def on_model_change(self, data, model, is_created, request):
        form_data = await request.form()
        new_password = (form_data.get("new_password") or "").strip()
        if new_password:
            model.password_hash = hash_password(new_password)
        elif is_created and not model.password_hash:
            model.password_hash = hash_password("123456")


class GradeAdmin(ModelView, model=models.Grade):
    name = "Оценка"
    name_plural = "Оценки"
    icon = "fa-solid fa-star"
    column_list = [models.Grade.id, models.Grade.user, models.Grade.subject,
                   models.Grade.mark, models.Grade.date]
    column_labels = {
        "user": "Студент", "subject": "Предмет", "mark": "Оценка",
        "date": "Дата", "teacher_name": "Преподаватель", "comment": "Комментарий",
    }
    form_columns = ["user", "subject", "mark", "date", "teacher_name", "comment"]


class HomeworkAdmin(ModelView, model=models.Homework):
    name = "Домашнее задание"
    name_plural = "Домашние задания"
    icon = "fa-solid fa-book-open"
    column_list = [models.Homework.id, models.Homework.group, models.Homework.subject,
                   models.Homework.due_date]
    form_columns = ["group", "subject", "task", "due_date", "teacher_name"]


class ApplicationAdmin(ModelView, model=models.Application):
    name = "Заявка"
    name_plural = "Заявки на поступление"
    icon = "fa-solid fa-envelope-open-text"
    column_list = [models.Application.id, models.Application.fio,
                   models.Application.phone, models.Application.created_at]
    can_create = False


class FeedbackAdmin(ModelView, model=models.FeedbackMessage):
    name = "Обращение"
    name_plural = "Обращения с сайта"
    icon = "fa-solid fa-comments"
    column_list = [models.FeedbackMessage.id, models.FeedbackMessage.name,
                   models.FeedbackMessage.contact, models.FeedbackMessage.topic,
                   models.FeedbackMessage.created_at, models.FeedbackMessage.is_processed]
    can_create = False
    form_columns = ["name", "contact", "topic", "message", "is_processed"]


admin = Admin(
    app,
    engine,
    base_url="/admin",
    title="КТТО — панель управления",
    authentication_backend=AdminAuth(),
)

for _view in (NewsAdmin, DocumentAdmin, ScheduleAdmin, GroupAdmin, UserAdmin,
              GradeAdmin, HomeworkAdmin, ApplicationAdmin, FeedbackAdmin):
    admin.add_view(_view)
