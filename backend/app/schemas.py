from typing import Any

from pydantic import BaseModel
from datetime import date, datetime

class UserCreate(BaseModel):
    name: str
    external_id: str | None = None  # Flutter Account.id (UUID)

class UserOut(BaseModel):
    id: int
    name: str
    external_id: str | None = None
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
    geometry: dict[str, Any] | None = None
    class Config:
        from_attributes = True


# Favorite schemas
class FavoriteBase(BaseModel):
    type: str  # 'place', 'road', 'route'
    name: str
    address: str | None = None
    lon: float | None = None
    lat: float | None = None
    place_data: dict[str, Any] | None = None
    road_name: str | None = None
    road_search_name: str | None = None
    road_osmids: list[str] | None = None
    road_distance_threshold: float | None = 15.0
    route_start: str | None = None
    route_end: str | None = None
    route_start_coords: dict[str, Any] | None = None
    route_end_coords: dict[str, Any] | None = None
    route_distance: float | None = None
    route_duration: float | None = None
    route_feature_collection: dict[str, Any] | None = None
    route_distance_threshold: float | None = 50.0
    recommendations: list[dict[str, Any]] | None = None
    notification_enabled: bool = False
    distance_threshold: float = 100.0


class FavoriteCreate(FavoriteBase):
    user_id: int | None = None  # 可選，如果提供了 external_id 則不需要


class FavoriteUpdate(BaseModel):
    notification_enabled: bool | None = None
    distance_threshold: float | None = None
    recommendations: list[dict[str, Any]] | None = None


class FavoriteOut(FavoriteBase):
    id: int
    user_id: int
    added_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True