from pydantic import BaseModel

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
