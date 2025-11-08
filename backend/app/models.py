from sqlalchemy import Column, Integer, String
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


class ConstructionNotice(Base):
    __tablename__ = "construction_notices"
    id = Column(Integer, primary_key=True, index=True)
    date_range = Column(String(200), nullable=True)  # 日期範圍
    name = Column(String(500), nullable=False)  # 工程名稱
    type = Column(String(200), nullable=True)  # 工程類型
    unit = Column(String(200), nullable=True)  # 執行單位
    road = Column(String(500), nullable=True)  # 道路/地點
    url = Column(String(1000), nullable=True)  # 詳細資訊連結