from pydantic import BaseModel
from datetime import date
from typing import Optional

# Тот самый класс, который мы пытаемся импортировать
class NewsSchema(BaseModel):
    id: int
    title: str
    description: str
    date: date
    image_url: Optional[str] = None

    class Config:
        from_attributes = True # Это позволяет Pydantic работать с моделями SQLAlchemy