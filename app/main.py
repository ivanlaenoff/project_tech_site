import os
import shutil
import uuid
from fastapi import FastAPI, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse  # НОВОЕ: добавил RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqladmin import Admin, ModelView
from wtforms import FileField

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
    
    # Получаем другие свежие новости (исключая открытую сейчас)
    other_news = db.query(models.News).filter(models.News.id != news_id).order_by(models.News.id.desc()).limit(5).all()
    
    # НОВОЕ: добавил add_user_context
    return templates.TemplateResponse(request, "news.html", {
        "request": request,
        "post": news_item,
        "images": images,
        "other_news": other_news,
        **add_user_context(request)
    })


@app.get("/all-news", response_class=HTMLResponse)
async def get_all_news(request: Request, page: int = 1, db: Session = Depends(get_db)):
    per_page = 6
    offset = (page - 1) * per_page
    total = db.query(models.News).count()
    news_items = db.query(models.News).order_by(models.News.id.desc()).offset(offset).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    # НОВОЕ: добавил add_user_context
    return templates.TemplateResponse(request, "all_news.html", {
        "request": request,
        "news": news_items,
        "current_page": page,
        "total_pages": total_pages,
        **add_user_context(request)
    })


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
    specialties=[
        {
            "id":"bank",
            "title":"Банковское дело",
            "desc":"Подготовка специалистов банковской сферы",
            "time":"2 года 10 месяцев"
        },
        {
            "id":"law",
            "title":"Юриспруденция",
            "desc":"Подготовка специалистов в области права",
            "time":"2 года 10 месяцев"
        },
        {
            "id":"cook",
            "title":"Поварское дело",
            "desc":"Технология приготовления пищи",
            "time":"3 года 10 месяцев"
        },
        {
            "id":"info",
            "title":"Информационные системы",
            "desc":"Разработка и сопровождение информационных систем",
            "time":"3 года 10 месяцев"
        },
        {
            "id":"finance",
            "title":"Финансы",
            "desc":"Финансовая деятельность организаций",
            "time":"2 года 10 месяцев"
        },
        {
            "id":"commerce",
            "title":"Коммерция",
            "desc":"Организация продаж и торговли",
            "time":"2 года 10 месяцев"
        }
    ]

    current=specialties[0]

    if item:
        for s in specialties:
            if s["id"]==item:
                current=s

    return templates.TemplateResponse(
        request,
        "specialties.html",
        {
            "request":request,
            "current":current,
            "specialties":specialties,
            **add_user_context(request)
        }
    )
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
    
    # Добавляем данные профиля в зависимости от роли
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


# ========== АДМИНКА ==========

class NewsAdmin(ModelView, model=models.News):
    column_list = [models.News.id, models.News.title, models.News.date]
    name_plural = "Новости"
    form_columns = ["title", "description", "date"]
    
    async def scaffold_form(self, *args, **kwargs):
        from wtforms import FileField, StringField
        form_class = await super().scaffold_form(*args, **kwargs)
        
        form_class.image_file = FileField("Загрузить картинку (обложка)")
        form_class.gallery_files = FileField(
            "Дополнительные фото (можно выбрать несколько)", 
            render_kw={"multiple": True}
        )
        form_class.date = StringField(
            "Дата",
            render_kw={"type": "date", "style": "width: 100%; padding: 8px;"}
        )
        return form_class
    
    async def on_model_change(self, data, model, is_created, request):
        from datetime import datetime
        form_data = await request.form()
        
        # Обложка
        file = form_data.get("image_file")
        if file and file.filename:
            ext = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
            filename = f"news_{uuid.uuid4().hex[:8]}.{ext}"
            filepath = os.path.join(STATIC_DIR, "news", filename)
            with open(filepath, "wb") as f:
                shutil.copyfileobj(file.file, f)
            model.image_url = f"/static/news/{filename}"
        
        # Дата
        if model.date:
            try:
                d = datetime.strptime(model.date, "%Y-%m-%d")
                model.date = d.strftime("%d %B %Y")
            except:
                pass
        
        self._pending_gallery = form_data.getlist("gallery_files")

    async def after_model_change(self, data, model, is_created, request):
        db = SessionLocal()
        try:
            for file in self._pending_gallery:
                if file and file.filename:
                    ext = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
                    filename = f"gallery_{uuid.uuid4().hex[:8]}.{ext}"
                    filepath = os.path.join(STATIC_DIR, "news", filename)
                    with open(filepath, "wb") as f:
                        shutil.copyfileobj(file.file, f)
                    
                    db.add(models.NewsImage(
                        news_id=model.id,
                        image_url=f"/static/news/{filename}"
                    ))
            db.commit()
        except Exception as e:
            db.rollback()
        finally:
            db.close()
            self._pending_gallery = []


class ApplicationAdmin(ModelView, model=models.Application):
    column_list = [models.Application.id, models.Application.fio, models.Application.phone, models.Application.created_at]
    name_plural = "Заявки на поступление"
    can_create = False


admin = Admin(app, engine, base_url="/admin")
admin.add_view(NewsAdmin)
admin.add_view(ApplicationAdmin)