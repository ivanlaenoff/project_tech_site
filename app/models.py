from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
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
    video_order = Column(Integer, nullable=True)  # Порядковый номер

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


# ======================================================================
# АККАУНТЫ
# ======================================================================

class UserRole(str, Enum):
    STUDENT = "student"
    PARENT = "parent"
    TEACHER = "teacher"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default=UserRole.STUDENT.value)
    is_active = Column(Integer, default=1)


class Group(Base):
    """Учебная группа (например, ИС-21)."""
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    specialty_id = Column(String, nullable=True)   # id из app/data.py SPECIALTIES
    course = Column(Integer, default=1)
    curator = Column(String, nullable=True)
    students_count = Column(Integer, default=25)

    def __repr__(self):
        return self.name


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    group_name = Column(String, nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    record_book = Column(String, nullable=True)

    user = relationship("User")
    group = relationship("Group")

    @property
    def full_name(self):
        return f"{self.last_name or ''} {self.first_name or ''}".strip()


class TeacherProfile(Base):
    __tablename__ = "teacher_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    middle_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    position = Column(String, nullable=True)
    subject = Column(String, nullable=True)

    user = relationship("User")

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join(p for p in parts if p)


class ParentProfile(Base):
    __tablename__ = "parent_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    student_id = Column(Integer, ForeignKey("student_profiles.id"), nullable=True)

    user = relationship("User")
    student = relationship("StudentProfile")

    @property
    def full_name(self):
        return f"{self.last_name or ''} {self.first_name or ''}".strip()


# ======================================================================
# РАСПИСАНИЕ, ДНЕВНИК
# ======================================================================

class Schedule(Base):
    """Пара в расписании группы."""
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    weekday = Column(Integer, nullable=False)      # 1 = понедельник ... 6 = суббота
    lesson_no = Column(Integer, nullable=False)    # 1..5
    subject = Column(String, nullable=False)
    teacher_name = Column(String, nullable=True)
    room = Column(String, nullable=True)
    lesson_type = Column(String, default="Практика")  # Лекция / Практика / Лабораторная
    subgroup = Column(String, nullable=True)

    group = relationship("Group")


class Grade(Base):
    """Оценка студента за занятие."""
    __tablename__ = "grades"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subject = Column(String, nullable=False)
    mark = Column(Integer, nullable=False)         # 2..5
    date = Column(String, nullable=True)           # YYYY-MM-DD
    teacher_name = Column(String, nullable=True)
    comment = Column(String, nullable=True)

    user = relationship("User")


class Homework(Base):
    """Домашнее задание для группы."""
    __tablename__ = "homework"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    subject = Column(String, nullable=False)
    task = Column(Text, nullable=False)
    due_date = Column(String, nullable=True)       # YYYY-MM-DD
    teacher_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("Group")


# ======================================================================
# ДОКУМЕНТЫ И ОБРАТНАЯ СВЯЗЬ
# ======================================================================

class DocumentFile(Base):
    """Документ из раздела «Документы» (загружается через админку)."""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    category = Column(String, default="Общие")
    description = Column(String, nullable=True)
    file_name = Column(String, nullable=True)
    file_url = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    order = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return self.title


class FeedbackMessage(Base):
    __tablename__ = "feedback_messages"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    contact = Column(String, nullable=False)
    topic = Column(String, nullable=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_processed = Column(Integer, default=0)
