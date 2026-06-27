from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime

class News(Base):
    __tablename__ = "news"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String)
    date = Column(String)
    image_url = Column(String, nullable=True)
    
    images = relationship("NewsImage", back_populates="news", cascade="all, delete-orphan")

class NewsImage(Base):
    __tablename__ = "news_images"
    id = Column(Integer, primary_key=True, index=True)
    news_id = Column(Integer, ForeignKey("news.id", ondelete="CASCADE"))
    image_url = Column(String)
    
    news = relationship("News", back_populates="images")
    
    def __repr__(self):
        # Показываем имя файла вместо объекта
        if self.image_url:
            filename = self.image_url.split('/')[-1]
            return f"📷 {filename}"
        return "📷 Без фото"
    
    def __str__(self):
        return self.__repr__()

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