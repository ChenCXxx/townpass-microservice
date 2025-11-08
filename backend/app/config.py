from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    DATABASE_URL: str
    # Update schedule: cron format (minute, hour, day, month, day_of_week)
    # Default: daily at 6:00 PM
    # Example: "0 18 * * *" = daily at 6 PM, "0 */6 * * *" = every 6 hours
    CONSTRUCTION_UPDATE_SCHEDULE: str = "0 18 * * *"  # Every day at 6 PM
    # Path to store construction.geojson file
    # Default: /app/data/construction.geojson (inside container)
    CONSTRUCTION_GEOJSON_PATH: str = str(Path("/app/data/construction.geojson"))

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
