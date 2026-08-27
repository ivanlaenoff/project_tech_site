import os
from pyexpat import model
import shutil
from typing import Optional
import uuid
from xml.parsers.expat import model
from fastapi import FastAPI, Depends, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Column, ForeignKey, Integer, String, cast, func, or_
from starlette.requests import Request
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session, relationship
from sqladmin import Admin, ModelView
from wtforms import FileField
from app.data import SPECIALTIES

import app.models as models
from app.database import engine, SessionLocal, Base

# НОВОЕ: импорты для аутентификации
from app.auth import (
    hash_password, verify_password, login_user, logout_user,
    get_current_user, require_auth, require_role, add_user_context,
    is_authenticated, get_current_user_role
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app = FastAPI()

os.makedirs(os.path.join(STATIC_DIR, "news"), exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "src"), exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/src", StaticFiles(directory=os.path.join(STATIC_DIR, "src")), name="src")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.add_middleware(SessionMiddleware, secret_key="some-secret-key")

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ========== РОУТЫ(пр) ==========
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    news_items = db.query(models.News).order_by(models.News.id.desc()).limit(6).all()
    # НОВОЕ: добавил add_user_context
    return templates.TemplateResponse(request, "index.html", {
        "request": request,
        "news": news_items,
        **add_user_context(request)
    })

@app.get("/news/{news_id}", response_class=HTMLResponse)
async def read_news_item(request: Request, news_id: int, db: Session = Depends(get_db)):
    news_item = db.query(models.News).filter(models.News.id == news_id).first()
    if not news_item:
        raise HTTPException(status_code=404, detail="Новость не найдена")
    
    images = db.query(models.NewsImage).filter(models.NewsImage.news_id == news_id).all()

    documents = db.query(models.NewsDocument).filter(
        models.NewsDocument.news_id == news_id
).all()
    
    # Получаем другие свежие новости (исключая открытую сейчас)
    other_news = db.query(models.News).filter(models.News.id != news_id).order_by(models.News.id.desc()).limit(5).all()
    
    # НОВОЕ: добавил add_user_context
    return templates.TemplateResponse(request, "news.html", {
        "request": request,
        "post": news_item,
        "images": images,
        "documents": documents,
        "other_news": other_news,
        **add_user_context(request)
    })

@app.get("/all_news", response_class=HTMLResponse)
def get_all_news(
    request: Request,
    page: int = 1, 
    date: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    per_page = 6
    query = db.query(models.News)
    
    if date:
        # date приходит в формате "YYYY-MM-DD" (например, "2026-06-16")
        # Конвертируем также в формат "DD.MM.YYYY" для надежности, если в базе точки
        parts = date.split('-')
        date_dotted = f"{parts[2]}.{parts[1]}.{parts[0]}" if len(parts) == 3 else ""
        
        # Фильтруем: ищем либо совпадение по строке, либо через функцию даты SQL
        query = query.filter(
            or_(
                cast(models.News.date, String).like(f"%{date}%"),
                cast(models.News.date, String).like(f"%{date_dotted}%")
            )
        )
        
    total_news = query.count()
    total_pages = (total_news + per_page - 1) // per_page
    
    news = query.offset((page - 1) * per_page).limit(per_page).all()
    
    user_ctx = {}
    try:
        if 'add_user_context' in globals():
            res = add_user_context(request)
            if isinstance(res, dict):
                user_ctx = res
    except Exception:
        pass

    context_data = {
        "request": request,
        "news": news,
        "current_page": page,
        "total_pages": max(total_pages, 1),
        "selected_date": date,
    }
    context_data.update(user_ctx)
    
    return templates.TemplateResponse(
        request=request,
        name="all_news.html",
        context=context_data
    )

@app.get("/about", response_class=HTMLResponse)
async def get_about_page(request: Request):
    # НОВОЕ: добавил add_user_context
    return templates.TemplateResponse(request, "about.html", {
        "request": request,
        **add_user_context(request)
    })


@app.get("/admission", response_class=HTMLResponse)
async def get_admission_page(request: Request):
    # НОВОЕ: добавил add_user_context
    return templates.TemplateResponse(request, "admission.html", {
        "request": request,
        **add_user_context(request)
    })


@app.get("/contacts", response_class=HTMLResponse)
async def get_contacts_page(request: Request):
    # НОВОЕ: добавил add_user_context
    return templates.TemplateResponse(request, "contacts.html", {
        "request": request,
        **add_user_context(request)
    })


@app.get("/students", response_class=HTMLResponse)
async def get_students_page(request: Request):
    # НОВОЕ: добавил add_user_context
    return templates.TemplateResponse(request, "students.html", {
        "request": request,
        **add_user_context(request)
    })


@app.get("/apply", response_class=HTMLResponse)
async def get_apply_page(request: Request):
    # НОВОЕ: добавил add_user_context
    return templates.TemplateResponse(request, "apply.html", {
        "request": request,
        **add_user_context(request)
    })


@app.post("/apply")
async def post_application(
    request: Request,
    fio: str = Form(...),
    phone: str = Form(...),
    db: Session = Depends(get_db)
):
    new_app = models.Application(fio=fio, phone=phone)
    db.add(new_app)
    db.commit()
    # НОВОЕ: добавил add_user_context
    return templates.TemplateResponse(request, "apply.html", {
        "request": request,
        "success": True,
        **add_user_context(request)
    })

@app.get("/specialties", response_class=HTMLResponse)
async def specialties_page(
    request: Request,
    item: str = None
):
    current = SPECIALTIES[0]

    if item:
        for s in SPECIALTIES:
            if s["id"] == item:
                current = s

    return templates.TemplateResponse(
        request,
        "specialties.html",
        {
            "request": request,
            "current": current,
            "specialties": SPECIALTIES,
            **add_user_context(request)
        }
    )

@app.get("/api/news-dates")
def get_news_dates(db: Session = Depends(get_db)):
    news_items = db.query(models.News).all()
    dates = set()
    
    for item in news_items:
        if item.date:
            # Поддержка формата datetime/date или строк вида "15.07.2026"
            if hasattr(item.date, 'strftime'):
                dates.add(item.date.strftime('%Y-%m-%d'))
            else:
                date_str = str(item.date).strip()
                parts = date_str.split('.')
                if len(parts) == 3:
                    # Конвертируем из DD.MM.YYYY в YYYY-MM-DD
                    dates.add(f"{parts[2]}-{parts[1]}-{parts[0]}")
                else:
                    dates.add(date_str)
                    
    return {"dates": list(dates)}

@app.get("/info", response_class=HTMLResponse)
async def get_info_page(request: Request):
    return templates.TemplateResponse(request, "info.html", {"request": request})

# ========== НОВЫЕ РОУТЫ ДЛЯ АУТЕНТИФИКАЦИИ ==========

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Страница входа"""
    return templates.TemplateResponse("login.html", {
        "request": request,
        **add_user_context(request)
    })


@app.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Обработка формы входа"""
    # Ищем пользователя по email
    user = db.query(models.User).filter(models.User.email == email).first()
    
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Пользователь не найден",
            **add_user_context(request)
        })
    
    # Проверяем пароль
    if not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Неверный пароль",
            **add_user_context(request)
        })
    
    # Проверяем, активен ли аккаунт
    if not user.is_active:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Аккаунт заблокирован",
            **add_user_context(request)
        })
    
    # Вход выполнен — сохраняем в сессию
    login_user(request, user.id, user.role.value)
    
    # Перенаправляем на главную
    return RedirectResponse(url="/", status_code=303)


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Страница регистрации"""
    return templates.TemplateResponse("register.html", {
        "request": request,
        **add_user_context(request)
    })


@app.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    role: str = Form(...),  # student, parent, teacher
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone: str = Form(...),
    group_name: str = Form(None),  # для студента
    student_full_name: str = Form(None),  # для родителя
    db: Session = Depends(get_db)
):
    """Обработка формы регистрации"""
    
    # Проверяем, что пароли совпадают
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Пароли не совпадают",
            **add_user_context(request)
        })
    
    # Проверяем, не занят ли email
    existing_user = db.query(models.User).filter(models.User.email == email).first()
    if existing_user:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Пользователь с таким email уже существует",
            **add_user_context(request)
        })
    
    # Создаём пользователя
    hashed_password = hash_password(password)
    new_user = models.User(
        email=email,
        password_hash=hashed_password,
        role=models.UserRole(role)
    )
    db.add(new_user)
    db.flush()  # Получаем ID пользователя
    
    # Создаём профиль в зависимости от роли
    if role == "student":
        profile = models.StudentProfile(
            user_id=new_user.id,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            group_name=group_name
        )
        db.add(profile)
        
    elif role == "parent":
        # Ищем студента по ФИО (упрощённо)
        student = None
        if student_full_name:
            parts = student_full_name.strip().split()
            if len(parts) >= 2:
                last_name_s = parts[0]
                first_name_s = parts[1]
                student = db.query(models.StudentProfile).filter(
                    models.StudentProfile.last_name == last_name_s,
                    models.StudentProfile.first_name == first_name_s
                ).first()
        
        profile = models.ParentProfile(
            user_id=new_user.id,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            student_id=student.id if student else None
        )
        db.add(profile)
        
    elif role == "teacher":
        profile = models.TeacherProfile(
            user_id=new_user.id,
            first_name=first_name,
            last_name=last_name,
            phone=phone
        )
        db.add(profile)
    
    db.commit()
    
    # Автоматически входим после регистрации
    login_user(request, new_user.id, new_user.role.value)
    
    return RedirectResponse(url="/", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    """Выход из системы"""
    logout_user(request)
    return RedirectResponse(url="/", status_code=303)


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    user: models.User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Личный кабинет пользователя"""
    context = {
        "request": request,
        "user": user,
        **add_user_context(request)
    }
    
    # данные профиля в зависимости от роли
    if user.role == models.UserRole.STUDENT:
        profile = db.query(models.StudentProfile).filter(
            models.StudentProfile.user_id == user.id
        ).first()
        context["profile"] = profile
        
    elif user.role == models.UserRole.PARENT:
        profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == user.id
        ).first()
        context["profile"] = profile
        
    elif user.role == models.UserRole.TEACHER:
        profile = db.query(models.TeacherProfile).filter(
            models.TeacherProfile.user_id == user.id
        ).first()
        context["profile"] = profile
    
    return templates.TemplateResponse("profile.html", context)


@app.get("/add-news", response_class=HTMLResponse)
async def add_news_page(
    request: Request,
    user: models.User = Depends(require_role("teacher")),  # Только для преподавателей
    db: Session = Depends(get_db)
):
    """Страница добавления новости (доступна только преподавателям)"""
    return templates.TemplateResponse("add_news.html", {
        "request": request,
        **add_user_context(request)
    })

# ====== ПЕСОЧНИЦА ДЛЯ ЭКСПЕРИМЕНТОВ ======
@app.get("/testindex", response_class=HTMLResponse)
async def sandbox(request: Request):
    return templates.TemplateResponse("testindex.html", {
        "request": request,
        **add_user_context(request)
    })
# ========== АДМИНКА ==========
class NewsAdmin(ModelView, model=models.News):
    column_list = [models.News.id, models.News.title, models.News.date]
    name_plural = "Новости"
    form_columns = [
        "title", 
        "description", 
        "date",
    ]
    
    async def scaffold_form(self, *args, **kwargs):
        from wtforms import FileField, StringField
        form_class = await super().scaffold_form(*args, **kwargs)
        
        # Добавляем поля в форму для рендеринга интерфейса, 
        # но SQLAlchemy не будет пытаться искать их в базе данных
        form_class.image_file = FileField("Загрузить картинку (обложка)")
        form_class.video_upload = FileField("Загрузить видео файл")
        form_class.gallery_files = FileField(
            "Дополнительные фото (можно выбрать несколько)", 
            render_kw={"multiple": True}
        )
        form_class.document_files = FileField(
            "Документы",
            render_kw={"multiple": True}
        )
        form_class.video_order = StringField(
            "Порядковый номер видео",
            default="0",
            render_kw={"style": "width: 100%; padding: 8px;"}
        )

        return form_class
    
    async def on_model_change(self, data, model, is_created, request):
        from datetime import datetime

        form_data = await request.form()
        print("ВСЕ ПОЛЯ И ФАЙЛЫ В ФОРМЕ:", list(form_data.keys()))
        for key in form_data.keys():
            print(f"Ключ: {key}, Значение: {form_data.get(key)}")
        print("ВСЕ ПОЛЯ И ФАЙЛЫ В ФОРМЕ:", list(form_data.keys()))
        
        # Обложка
        file = form_data.get("image_file")
        if file and hasattr(file, "filename") and file.filename:
            ext = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
            filename = f"news_{uuid.uuid4().hex[:8]}.{ext}"
            filepath = os.path.join(STATIC_DIR, "news", filename)
            with open(filepath, "wb") as f:
                shutil.copyfileobj(file.file, f)
            model.image_url = f"/static/news/{filename}"
        
        # Видео файл (берем из video_upload и пишем строковый путь в model.video_url)
        video_file = form_data.get("video_upload")
        if video_file and hasattr(video_file, "filename") and video_file.filename:
            ext = video_file.filename.split('.')[-1] if '.' in video_file.filename else 'mp4'
            filename = f"video_{uuid.uuid4().hex[:8]}.{ext}"
            
            video_dir = os.path.join(STATIC_DIR, "news", "videos")
            os.makedirs(video_dir, exist_ok=True)
            
            filepath = os.path.join(video_dir, filename)
            with open(filepath, "wb") as f:
                shutil.copyfileobj(video_file.file, f)
            
            model.video_url = f"/static/news/videos/{filename}"

            print("УСПЕХ! ЗАПИСАЛИ В MODEL.VIDEO_URL:", model.video_url)
        # Дата
        if model.date:
            try:
                d = datetime.strptime(model.date, "%Y-%m-%d")
                model.date = d.strftime("%d %B %Y")
            except:
                pass
        
        # Порядковый номер видео
        raw_order = form_data.get("video_order")
        model.video_order = int(raw_order) if raw_order and raw_order.isdigit() else 0
        
        self._pending_gallery = form_data.getlist("gallery_files")
        self._pending_documents = form_data.getlist("document_files")

    async def after_model_change(self, data, model, is_created, request):
        db = SessionLocal()
        try:
            for file in self._pending_gallery:
                if file and hasattr(file, "filename") and file.filename:
                    ext = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
                    filename = f"gallery_{uuid.uuid4().hex[:8]}.{ext}"
                    filepath = os.path.join(STATIC_DIR, "news", filename)
                    with open(filepath, "wb") as f:
                        shutil.copyfileobj(file.file, f)
                    
                    db.add(models.NewsImage(
                        news_id=model.id,
                        image_url=f"/static/news/{filename}"
                    ))

            for file in self._pending_documents:
                if file and hasattr(file, "filename") and file.filename:
                    ext = file.filename.split(".")[-1]
                    filename = f"doc_{uuid.uuid4().hex[:8]}.{ext}"
                    filepath = os.path.join(STATIC_DIR, "news", filename)
                    with open(filepath, "wb") as f:
                        shutil.copyfileobj(file.file, f)

                    db.add(models.NewsDocument(
                        news_id=model.id,
                        file_name=file.filename,
                        file_url=f"/static/news/{filename}"
                    ))
            db.commit()
        except Exception as e:
            db.rollback()
        finally:
            db.close()
            self._pending_gallery = []
            self._pending_documents = []

class ApplicationAdmin(ModelView, model=models.Application):
    column_list = [models.Application.id, models.Application.fio, models.Application.phone, models.Application.created_at]
    name_plural = "Заявки на поступление"
    can_create = False


admin = Admin(app, engine, base_url="/admin")
admin.add_view(NewsAdmin)
admin.add_view(ApplicationAdmin)

class ApplicationAdmin(ModelView, model=models.Application):
    column_list = [models.Application.id, models.Application.fio, models.Application.phone, models.Application.created_at]
    name_plural = "Заявки на поступление"
    can_create = False


admin = Admin(app, engine, base_url="/admin")
admin.add_view(NewsAdmin)
admin.add_view(ApplicationAdmin)