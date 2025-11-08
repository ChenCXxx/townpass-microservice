import requests
from bs4 import BeautifulSoup
import urllib3
import json
import os
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging

# Disable SSL warnings (not recommended for production)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Constants
BASE_URL = "https://dig.taipei/Tpdig"
MAP_URL = f"{BASE_URL}/Map/ShowPublic.aspx"
USER_ID = "tpdig"


def get_app_key() -> str:
    """Fetch the AppKey from the public map page."""
    try:
        response = requests.get(MAP_URL, verify=False, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        app_key_input = soup.find("input", id="AppKey")
        
        if app_key_input is None:
            raise ValueError("AppKey input not found on the page")
        
        return app_key_input["value"]
    except Exception as e:
        logger.error(f"Failed to get app key: {e}")
        raise


def get_app_work(user_id: str, key: str) -> List[Dict[str, Any]]:
    """Fetch app work data and return as JSON list."""
    try:
        url = f"{BASE_URL}/APP/GetAppWork.ashx?userid={user_id}&key={key}&isrpic=1&isgland="
        response = requests.get(url, verify=False, timeout=30)
        response.raise_for_status()
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Failed to get app work data: {e}")
        raise


def convert_to_geojson(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert the API response data to GeoJSON format."""
    features = []
    
    for item in data:
        # Skip items without valid coordinates
        if item.get("LAT") is None or item.get("LON") is None:
            continue
        
        try:
            lat = float(item["LAT"])
            lon = float(item["LON"])
        except (ValueError, TypeError):
            logger.warning(f"Skipping item with invalid coordinates: {item.get('AC_NO', 'unknown')}")
            continue
        
        # Create GeoJSON feature
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]  # GeoJSON uses [lon, lat] order
            },
            "properties": {
                k: v for k, v in item.items() 
                if k not in ["LAT", "LON"]  # Exclude LAT/LON from properties
            }
        }
        features.append(feature)
    
    return {
        "type": "FeatureCollection",
        "features": features
    }


def save_geojson(geojson_data: Dict[str, Any], filepath: str) -> None:
    """Save GeoJSON data to a file."""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Write file atomically (write to temp file first, then rename)
        temp_filepath = f"{filepath}.tmp"
        with open(temp_filepath, "w", encoding="utf-8") as f:
            json.dump(geojson_data, f, ensure_ascii=False, indent=2)
        
        # Atomic rename
        os.replace(temp_filepath, filepath)
        logger.info(f"GeoJSON saved successfully to {filepath} ({len(geojson_data['features'])} features)")
    except Exception as e:
        logger.error(f"Failed to save GeoJSON to {filepath}: {e}")
        raise


def fetch_construction_geojson() -> Dict[str, Any]:
    """
    Fetch construction data and convert to GeoJSON format.
    
    Returns:
        GeoJSON dictionary
    """
    logger.info("Fetching construction data from API...")
    
    # Get app key
    app_key = get_app_key()
    
    # Fetch data
    data = get_app_work(USER_ID, app_key)
    logger.info(f"Fetched {len(data)} records from API")
    
    # Convert to GeoJSON
    geojson = convert_to_geojson(data)
    logger.info(f"Converted to GeoJSON with {len(geojson['features'])} features")
    
    return geojson


def get_construction_geojson(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Read construction GeoJSON data from file.
    
    Args:
        file_path: Path to the GeoJSON file
        
    Returns:
        GeoJSON dictionary or None if file doesn't exist or can't be read
    """
    try:
        if not os.path.exists(file_path):
            logger.warning(f"Construction GeoJSON file not found: {file_path}")
            return None
        
        with open(file_path, "r", encoding="utf-8") as f:
            geojson = json.load(f)
            logger.debug(f"Loaded construction GeoJSON from {file_path}")
            return geojson
    except Exception as e:
        logger.error(f"Error reading construction GeoJSON file: {e}", exc_info=True)
        return None


def update_construction_geojson_file(file_path: str) -> bool:
    """
    Update construction.geojson file with latest data.
    
    Args:
        file_path: Full path to the output GeoJSON file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        geojson = fetch_construction_geojson()
        save_geojson(geojson, file_path)
        logger.info(f"Construction data file updated successfully: {file_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating construction file: {e}", exc_info=True)
        return False

