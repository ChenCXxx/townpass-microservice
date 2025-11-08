from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from typing import Dict, Any
from ..database import get_db
from .. import models, schemas
from ..config import settings
from ..services.construction_scraper import get_construction_geojson, update_construction_geojson_file
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter()

# test for echo
@router.post("/echo")
def echo(payload: dict):
    return {"you sent": payload}

@router.get("/hello")
def hello():
    return {"message": "Hello, Taipei Hackathon!"}

@router.get("/users", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).order_by(models.User.id).all()

@router.post("/users", response_model=schemas.UserOut)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    u = models.User(name=payload.name)
    db.add(u); db.commit(); db.refresh(u); return u


# TestRecord endpoints
@router.get("/test_records", response_model=list[schemas.TestOut])
def list_test_records(db: Session = Depends(get_db)):
    return db.query(models.TestRecord).order_by(models.TestRecord.id).all()


@router.post("/test_records", response_model=schemas.TestOut)
def create_test_record(payload: schemas.TestCreate, db: Session = Depends(get_db)):
    tr = models.TestRecord(title=payload.title, description=payload.description)
    db.add(tr)
    db.commit()
    db.refresh(tr)
    return tr

@router.get("/construction/geojson", response_model=Dict[str, Any])
def get_construction_data(response: Response):
    """Get construction data as GeoJSON from file. If file doesn't exist, update it first."""
    geojson = get_construction_geojson(settings.CONSTRUCTION_GEOJSON_PATH)
    
    # If file doesn't exist, try to update it first
    if geojson is None:
        logger.info("Construction GeoJSON file not found, attempting to update...")
        try:
            # Ensure data directory exists
            data_dir = os.path.dirname(settings.CONSTRUCTION_GEOJSON_PATH)
            os.makedirs(data_dir, exist_ok=True)
            
            # Try to update the file
            success = update_construction_geojson_file(settings.CONSTRUCTION_GEOJSON_PATH)
            if success:
                # Read the newly created file
                geojson = get_construction_geojson(settings.CONSTRUCTION_GEOJSON_PATH)
                if geojson is not None:
                    logger.info("Successfully updated and loaded construction data")
                    return geojson
            
            # If update failed or file still doesn't exist
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"error": "Construction data not available and update failed"}
        except Exception as e:
            logger.error(f"Error updating construction data: {e}", exc_info=True)
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"error": f"Failed to update construction data: {str(e)}"}
    
    return geojson


@router.get("/construction/update", response_model=Dict[str, Any])
def manual_update():
    """Manual trigger for construction data update (for testing/admin)"""
    try:
        # Ensure data directory exists
        data_dir = os.path.dirname(settings.CONSTRUCTION_GEOJSON_PATH)
        os.makedirs(data_dir, exist_ok=True)
        
        success = update_construction_geojson_file(settings.CONSTRUCTION_GEOJSON_PATH)
        if success:
            geojson = get_construction_geojson(settings.CONSTRUCTION_GEOJSON_PATH)
            feature_count = len(geojson['features']) if geojson else 0
            return {
                "status": "success",
                "message": "Construction data updated successfully",
                "feature_count": feature_count
            }
        else:
            return {"status": "error", "message": "Failed to update construction data"}
    except Exception as e:
        logger.error(f"Manual update failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# Construction Notices endpoints
@router.get("/construction/notices", response_model=list[schemas.ConstructionNoticeOut])
def list_construction_notices(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """獲取施工通知列表"""
    notices = db.query(models.ConstructionNotice).offset(skip).limit(limit).all()
    return notices


@router.get("/construction/notices/update", response_model=Dict[str, Any])
def update_construction_notices_endpoint(
    db: Session = Depends(get_db),
    max_pages: int = None,
    clear_existing: bool = True
):
    """手動觸發更新施工通知資料（爬取並保存）"""
    from ..services.notice_contruction import update_construction_notices
    try:
        result = update_construction_notices(db, max_pages=max_pages, clear_existing=clear_existing)
        return result
    except Exception as e:
        logger.error(f"Update construction notices failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}