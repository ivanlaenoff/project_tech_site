import os
import shutil
import uuid
from fastapi import FastAPI, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqladmin import Admin, ModelView
from wtforms import FileField

import app.models as models
from app.database import engine, SessionLocal, Base

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

# ========== РОУТЫ ==========
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    news_items = db.query(models.News).order_by(models.News.id.desc()).limit(6).all()
    return templates.TemplateResponse(request, "index.html", {"request": request, "news": news_items})

@app.get("/news/{news_id}", response_class=HTMLResponse)
async def read_news_item(request: Request, news_id: int, db: Session = Depends(get_db)):
    news_item = db.query(models.News).filter(models.News.id == news_id).first()
    if not news_item:
        raise HTTPException(status_code=404, detail="Новость не найдена")
    
    images = db.query(models.NewsImage).filter(models.NewsImage.news_id == news_id).all()
    
    # Получаем другие свежие новости (исключая открытую сейчас)
    other_news = db.query(models.News).filter(models.News.id != news_id).order_by(models.News.id.desc()).limit(5).all()
    
    return templates.TemplateResponse(request, "news.html", {
        "request": request,
        "post": news_item,
        "images": images,
        "other_news": other_news  # Передаем список в HTML
    })

@app.get("/all-news", response_class=HTMLResponse)
async def get_all_news(request: Request, page: int = 1, db: Session = Depends(get_db)):
    per_page = 6
    offset = (page - 1) * per_page
    total = db.query(models.News).count()
    news_items = db.query(models.News).order_by(models.News.id.desc()).offset(offset).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    return templates.TemplateResponse(request, "all_news.html", {
        "request": request,
        "news": news_items,
        "current_page": page,
        "total_pages": total_pages
    })

@app.get("/about", response_class=HTMLResponse)
async def get_about_page(request: Request):
    return templates.TemplateResponse(request, "about.html", {"request": request})

@app.get("/admission", response_class=HTMLResponse)
async def get_admission_page(request: Request):
    return templates.TemplateResponse(request, "admission.html", {"request": request})

@app.get("/info", response_class=HTMLResponse)
async def get_info_page(request: Request):
    return templates.TemplateResponse(request, "info.html", {"request": request})

@app.get("/contacts", response_class=HTMLResponse)
async def get_contacts_page(request: Request):
    return templates.TemplateResponse(request, "contacts.html", {"request": request})

@app.get("/students", response_class=HTMLResponse)
async def get_students_page(request: Request):
    return templates.TemplateResponse(request, "students.html", {"request": request})

@app.get("/apply", response_class=HTMLResponse)
async def get_apply_page(request: Request):
    return templates.TemplateResponse(request, "apply.html", {"request": request})

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
    return templates.TemplateResponse(request, "apply.html", {"request": request, "success": True})

# ========== АДМИНКА ==========
class NewsAdmin(ModelView, model=models.News):
    column_list = [models.News.id, models.News.title, models.News.date]
    name_plural = "Новости"
    form_columns = ["title", "description", "date"]  # Только эти поля в форме
    
    async def scaffold_form(self, *args, **kwargs):
        from wtforms import FileField, StringField
        form_class = await super().scaffold_form(*args, **kwargs)
        
        form_class.image_file = FileField("📸 Загрузить картинку (обложка)")
        form_class.gallery_files = FileField(
            "📁 Дополнительные фото (можно выбрать несколько)", 
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