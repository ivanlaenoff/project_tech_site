from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime
from enum import Enum

class News(Base):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String)
    date = Column(String)
    image_url = Column(String, nullable=True)
    video_url = Column(String, nullable=True)  # Путь к файлу видео
    video_order = Column(Integer, nullable=True) # Порядковый номер

    images = relationship(
        "NewsImage",
        back_populates="news",
        cascade="all, delete-orphan"
    )

    documents = relationship(
        "NewsDocument",
        back_populates="news",
        cascade="all, delete-orphan"
    )

class NewsImage(Base):
    __tablename__ = "news_images"

    id = Column(Integer, primary_key=True, index=True)
    news_id = Column(Integer, ForeignKey("news.id", ondelete="CASCADE"))
    image_url = Column(String)
    order = Column(Integer, default=0)

    news = relationship("News", back_populates="images")

    def __repr__(self):
        if self.image_url:
            filename = self.image_url.split("/")[-1]
            return f"📷 {filename}"
        return "📷 Без фото"


    def __str__(self):
        return self.__repr__()

    
class NewsDocument(Base):
    __tablename__ = "news_documents"

    id = Column(Integer, primary_key=True, index=True)
    news_id = Column(Integer, ForeignKey("news.id", ondelete="CASCADE"))
    file_name = Column(String)
    file_url = Column(String)

    news = relationship("News", back_populates="documents")


class Specialty(Base):
    __tablename__ = "specialties"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    description = Column(String)
    icon_url = Column(String)

class Application(Base):
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True, index=True)
    fio = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserRole(str, Enum):
    STUDENT = "student"
    PARENT = "parent"
    TEACHER = "teacher"


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(
        String,
        unique=True,
        nullable=False
    )
    password_hash = Column(
        String,
        nullable=False
    )
    role = Column(
        String,
        default=UserRole.STUDENT.value
    )
    is_active = Column(
        Integer,
        default=1
    )
