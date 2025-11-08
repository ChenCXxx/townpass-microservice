from sqlalchemy import Column, Integer, String, Boolean, Float, JSON, Date
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)


class TestRecord(Base):
    __tablename__ = "test_records"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(String(1000), nullable=True)


class RoadSegment(Base):
    __tablename__ = "road_segments"

    id = Column(Integer, primary_key=True, index=True)
    osmid = Column(String(255), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=True, index=True)
    highway = Column(String(50), nullable=True, index=True)
    lanes = Column(String(50), nullable=True)
    oneway = Column(Boolean, nullable=True)
    length_m = Column(Float, nullable=True)
    properties = Column(JSON, nullable=True)
    geometry = Column(JSON, nullable=False)

class ConstructionNotice(Base):
    __tablename__ = "construction_notices"
    id = Column(Integer, primary_key=True, index=True)
    start_date = Column(Date, nullable=True)  # 起始日期
    end_date = Column(Date, nullable=True)  # 結束日期
    name = Column(String(500), nullable=False)  # 工程名稱
    type = Column(String(200), nullable=True)  # 工程類型
    unit = Column(String(200), nullable=True)  # 執行單位
    road = Column(String(500), nullable=True)  # 道路/地點
    url = Column(String(1000), nullable=True)  # 詳細資訊連結
    geometry = Column(JSON, nullable=True)  # GeoJSON 格式的幾何資料（Polygon 或 LineString）