from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import logging
import sys
from .database import Base, engine, SessionLocal
from .routers.api import router
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
    except Exception as e:
        logger.error(f"Failed to check/update construction notices: {e}", exc_info=True)
        logger.warning("Application will continue to start, but construction notices may be unavailable")
    finally:
        db.close()
    
    # Setup scheduled task
    # Parse cron schedule: "minute hour day month day_of_week"
    # Example: "0 2 * * *" = daily at 2:00 AM
    schedule_parts = settings.CONSTRUCTION_UPDATE_SCHEDULE.split()
    if len(schedule_parts) == 5:
        minute, hour, day, month, day_of_week = schedule_parts
        scheduler.add_job(
            scheduled_update,
            trigger=CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week
            ),
            id="construction_update",
            name="Update construction.geojson",
            replace_existing=True
        )
        logger.info(f"Scheduled construction data update: {settings.CONSTRUCTION_UPDATE_SCHEDULE}")
    else:
        logger.warning(f"Invalid schedule format: {settings.CONSTRUCTION_UPDATE_SCHEDULE}. Using default: daily at 2 AM")
        scheduler.add_job(
            scheduled_update,
            trigger=CronTrigger(hour=2, minute=0),
            id="construction_update",
            name="Update construction.geojson",
            replace_existing=True
        )
    
    # Setup construction notices scheduled task (daily at 6:00 PM)
    scheduler.add_job(
        scheduled_notice_update,
        trigger=CronTrigger(hour=18, minute=0),  # 每天下午6點
        id="construction_notices_update",
        name="Update construction notices",
        replace_existing=True
    )
    logger.info("Scheduled construction notices update: daily at 6:00 PM (18:00)")
    
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

@app.get("/")
def read_root():
    return {"message": "Welcome to the Taipei Hackathon Microservice!"}
