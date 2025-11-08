from pydantic import BaseModel
from datetime import date

class UserCreate(BaseModel):
    name: str

class UserOut(BaseModel):
    id: int
    name: str
    class Config: orm_mode = True


class TestCreate(BaseModel):
    title: str
    description: str | None = None


class TestOut(BaseModel):
    id: int
    title: str
    description: str | None = None
    class Config: orm_mode = True


class ConstructionNoticeOut(BaseModel):
    id: int
    start_date: date | None = None
    end_date: date | None = None
    name: str
    type: str | None = None
    unit: str | None = None
    road: str | None = None
    url: str | None = None
    class Config: orm_mode = True