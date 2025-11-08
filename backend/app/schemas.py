from typing import Any

from pydantic import BaseModel
from datetime import date

class UserCreate(BaseModel):
    name: str

class UserOut(BaseModel):
    id: int
    name: str
    class Config:
        from_attributes = True


class TestCreate(BaseModel):
    title: str
    description: str | None = None


class TestOut(BaseModel):
    id: int
    title: str
    description: str | None = None
    class Config:
        from_attributes = True


class RoadSegmentBase(BaseModel):
    name: str | None = None
    highway: str | None = None
    lanes: str | None = None
    oneway: bool | None = None
    length_m: float | None = None
    properties: dict[str, Any] | None = None
    geometry: dict[str, Any]


class RoadSegmentCreate(RoadSegmentBase):
    osmid: str


class RoadSegmentOut(RoadSegmentBase):
    id: int
    osmid: str

    class Config:
        from_attributes = True


class ConstructionNoticeOut(BaseModel):
    id: int
    start_date: date | None = None
    end_date: date | None = None
    name: str
    type: str | None = None
    unit: str | None = None
    road: str | None = None
    url: str | None = None
    geometry: dict[str, Any] | None = None  # GeoJSON 格式
    class Config:
        from_attributes = True