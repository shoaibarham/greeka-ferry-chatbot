import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from config import DEFAULT_DATA_PATH
from sqlite_loader import load_data

logger = logging.getLogger(__name__)

def parse_date(date_string: str) -> datetime.date:
    """Convert a date string to a datetime.date object."""
    return datetime.strptime(date_string, "%Y-%m-%d").date()

def parse_vessel_key(vessel_key: str) -> tuple:
    """Parse a vessel key into code and name."""
    parts = vessel_key.split("___")
    if len(parts) == 2:
        return parts[0], parts[1]
    return vessel_key, vessel_key  # Fallback

def parse_accommodation_key(accommodation_key: str) -> tuple:
    """Parse an accommodation key into code and name."""
    parts = accommodation_key.split("___")
    if len(parts) == 2:
        return parts[0], parts[1]
    return accommodation_key, accommodation_key  # Fallback

def load_ferry_data(file_path: str = DEFAULT_DATA_PATH) -> List[Dict[str, Any]]:
    """Load ferry data from JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        logger.error(f"Failed to load ferry data from {file_path}: {str(e)}")
        raise

def update_ferry_data(file_path: str = DEFAULT_DATA_PATH) -> str:
    """
    Update the database with the latest ferry data.
    This function will clear existing data and reload from the specified file.
    """
    try:
        # Use SQLite loader to load data directly into the database
        logger.info(f"Loading ferry data from {file_path} into the database...")
        result = load_data(json_path=file_path, db_path='gtfs.db')
        
        # Log the successful update
        update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("data_updates.log", "a") as f:
            f.write(f"{update_time} - INFO - Successfully updated ferry data from {file_path}\n")
        
        logger.info("Ferry data update completed successfully.")
        return f"Successfully updated ferry data using SQLite loader from {file_path}"
    
    except Exception as e:
        logger.error(f"Error updating ferry data: {str(e)}", exc_info=True)
        raise
