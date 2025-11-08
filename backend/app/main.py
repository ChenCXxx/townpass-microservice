from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import logging
import sys
import asyncio
from .database import Base, engine, SessionLocal
from .routers.api import router
from .routers.websocket import router as websocket_router, check_and_notify_all_users
from .config import settings
from .services.construction_scraper import update_construction_geojson_file
from .services.notice_contruction import update_construction_notices
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    # datefmt="%H:%M:%S",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Initialize scheduler
scheduler = BackgroundScheduler()

def scheduled_update():
    """Scheduled task to update construction.geojson file"""
    logger.info(f"Running scheduled construction data update...")
    # Ensure data directory exists
    data_dir = os.path.dirname(settings.CONSTRUCTION_GEOJSON_PATH)
    os.makedirs(data_dir, exist_ok=True)
    
    success = update_construction_geojson_file(settings.CONSTRUCTION_GEOJSON_PATH)
    if success:
        logger.info("Scheduled update completed successfully")
    else:
        logger.error("Scheduled update failed")

def scheduled_notice_update():
    """Scheduled task to update construction notices"""
    logger.info("Running scheduled construction notices update...")
    db = SessionLocal()
    try:
        result = update_construction_notices(db, max_pages=None, clear_existing=False)
        if result.get("status") == "success":
            logger.info(f"Construction notices update completed: scraped {result.get('scraped_count', 0)}, saved {result.get('saved_count', 0)}")
        else:
            logger.error(f"Construction notices update failed: {result.get('message', 'Unknown error')}")
    except Exception as e:
        logger.error(f"Construction notices update failed with exception: {e}", exc_info=True)
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    # Startup
    logger.info("=" * 60)
    logger.info("Application starting up...")
    logger.info("=" * 60)
    
    # Ensure data directory exists
    data_dir = os.path.dirname(settings.CONSTRUCTION_GEOJSON_PATH)
    os.makedirs(data_dir, exist_ok=True)
    logger.info(f"Data directory ensured: {data_dir}")
    
    # Run initial update on startup (create/update file) - BLOCKING
    # This must complete before the application accepts requests
    logger.info("Running initial construction data update on startup...")
    try:
        success = update_construction_geojson_file(settings.CONSTRUCTION_GEOJSON_PATH)
        if success:
            logger.info("Initial construction data update completed successfully")
        else:
            logger.error("Initial construction data update failed (check logs above for details)")
            logger.warning("Application will continue to start, but construction data may be unavailable")
    except Exception as e:
        logger.error(f"Initial update failed with exception: {e}", exc_info=True)
        logger.warning("Application will continue to start, but construction data may be unavailable")
    
    # Check if construction notices exist in database, only update if empty
    logger.info("Checking construction notices in database...")
    db = SessionLocal()
    try:
        from .models import ConstructionNotice
        from .services.notice_contruction import update_construction_notices, update_missing_geometries
        
        notice_count = db.query(ConstructionNotice).count()
        if notice_count == 0:
            logger.info("No construction notices found in database. Running initial update...")
            result = update_construction_notices(db, max_pages=None, clear_existing=True)
            if result.get("status") == "success":
                logger.info(f"Initial construction notices update completed: scraped {result.get('scraped_count', 0)}, saved {result.get('saved_count', 0)}")
            else:
                logger.error(f"Initial construction notices update failed: {result.get('message', 'Unknown error')}")
                logger.warning("Application will continue to start, but construction notices may be unavailable")
        else:
            logger.info(f"Found {notice_count} construction notices in database. Skipping initial update.")
            
            # 檢查並更新缺少 geometry 的記錄
            geometry_result = update_missing_geometries(db)
            if geometry_result.get("status") == "success":
                updated_count = geometry_result.get('updated_count', 0)
                failed_count = geometry_result.get('failed_count', 0)
                total_missing = geometry_result.get('total', 0)
                if total_missing > 0:
                    logger.info(f"Geometry 更新完成: 發現 {total_missing} 筆缺少 geometry 的記錄，成功更新 {updated_count} 筆，失敗 {failed_count} 筆")
                else:
                    logger.info("所有施工通知記錄都已包含 geometry 資料")
            else:
                logger.error(f"Geometry 更新失敗: {geometry_result.get('message', 'Unknown error')}")
                logger.warning("Application will continue to start, but some notices may lack geometry")
    except Exception as e:
        logger.error(f"Failed to check/update construction notices: {e}", exc_info=True)
        logger.warning("Application will continue to start, but construction notices may be unavailable")
    finally:
        db.close()
    
    # Initialize default user if not exists
    logger.info("Checking default user in database...")
    db = SessionLocal()
    try:
        from .models import User
        
        default_external_id = "7f3562f4-bb3f-4ec7-89b9-da3b4b5ff250"
        existing_user = db.query(User).filter(User.external_id == default_external_id).first()
        
        if not existing_user:
            logger.info(f"Default user with external_id {default_external_id} not found. Creating...")
            default_user = User(
                name="Default User",
                external_id=default_external_id
            )
            db.add(default_user)
            db.commit()
            db.refresh(default_user)
            logger.info(f"Default user created successfully with id: {default_user.id}")
        else:
            logger.info(f"Default user already exists with id: {existing_user.id}")
    except Exception as e:
        logger.error(f"Failed to initialize default user: {e}", exc_info=True)
        logger.warning("Application will continue to start, but default user may be unavailable")
        db.rollback()
    finally:
        db.close()
    
    # Setup scheduled tasks using CONSTRUCTION_UPDATE_SCHEDULE
    # Parse cron schedule: "minute hour day month day_of_week"
    # Example: "0 18 * * *" = daily at 6:00 PM, "0 */6 * * *" = every 6 hours
    schedule_parts = settings.CONSTRUCTION_UPDATE_SCHEDULE.split()
    
    def parse_cron_value(value: str):
        """Parse cron value: '*' -> None, otherwise return as string (supports '*/6', '0-5', etc.)"""
        return None if value == '*' else value
    
    if len(schedule_parts) == 5:
        minute, hour, day, month, day_of_week = schedule_parts
        # Create trigger from cron string
        trigger = CronTrigger(
            minute=parse_cron_value(minute),
            hour=parse_cron_value(hour),
            day=parse_cron_value(day),
            month=parse_cron_value(month),
            day_of_week=parse_cron_value(day_of_week)
        )
    else:
        # Fallback to default if format is invalid
        logger.warning(f"Invalid schedule format: {settings.CONSTRUCTION_UPDATE_SCHEDULE}. Using default: daily at 6 PM")
        trigger = CronTrigger(hour=18, minute=0)
    
    # Add both scheduled tasks with the same trigger
    scheduler.add_job(
        scheduled_update,
        trigger=trigger,
        id="construction_update",
        name="Update construction.geojson",
        replace_existing=True
    )
    logger.info(f"Scheduled construction data update: {settings.CONSTRUCTION_UPDATE_SCHEDULE}")
    
    scheduler.add_job(
        scheduled_notice_update,
        trigger=trigger,
        id="construction_notices_update",
        name="Update construction notices",
        replace_existing=True
    )
    logger.info(f"Scheduled construction notices update: {settings.CONSTRUCTION_UPDATE_SCHEDULE}")
    
    # 添加定期檢查並推送通知的任務（每5秒檢查一次）
    # 取得目前的事件迴圈，讓 WebSocket 推播在同一個 loop 中執行，避免跨執行緒存取
    loop = asyncio.get_running_loop()

    def check_and_notify_async_safe():
        """在主事件迴圈中執行推播檢查，確保 WebSocket 操作 thread-safe"""
        try:
            future = asyncio.run_coroutine_threadsafe(check_and_notify_all_users(), loop)
            future.result()
        except Exception as e:
            logger.error(f"Error running check_and_notify_all_users in event loop: {e}", exc_info=True)

    # 使用 IntervalTrigger 每 5 秒執行一次
    scheduler.add_job(
        check_and_notify_async_safe,
        trigger=IntervalTrigger(seconds=5),
        id="construction_notification_check",
        name="Check and notify construction alerts",
        replace_existing=True
    )
    logger.info("Scheduled construction notification check: every 5 seconds")
    
    scheduler.start()
    logger.info("=" * 60)
    logger.info("Application startup completed successfully!")
    logger.info("=" * 60)
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    scheduler.shutdown()
    logger.info("Scheduler stopped")

app = FastAPI(
    title="Taipei Hackathon Microservice",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/docs/openapi.json",
    lifespan=lifespan,
)

origins = [
    "*",
    "http://localhost:5173",
    "http://localhost:4173",
    "http://localhost:3000",
    "http://localhost:8080",
    "https://townpass-microservice.web.app",
    "https://townpass-microservice.firebaseapp.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api", tags=["API"])
app.include_router(websocket_router, tags=["WebSocket"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the Taipei Hackathon Microservice!"}
