"""
Initialize ferry database with data from the provided JSON file.
This script should be run once to populate the database.
"""

import os
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_data_exists():
    """Check if there is already data in the database."""
    from app import app
    from ext import db
    from models import FerryCompany, Port, Vessel, FerryRoute, Schedule, Accommodation
    
    with app.app_context():
        route_count = FerryRoute.query.count()
        company_count = FerryCompany.query.count()
        port_count = Port.query.count()
        
        data_exists = route_count > 0 and company_count > 0 and port_count > 0
        
        if data_exists:
            logger.info(f"Database already contains data: {route_count} routes, {company_count} companies, {port_count} ports")
            
        return data_exists

def main():
    """Initialize the database with ferry data."""
    from data_processor import update_ferry_data
    from config import DEFAULT_DATA_PATH
    
    # Create a log file for data updates
    log_file = "data_updates.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    
    logger.info("Starting database initialization...")
    
    # Check if data already exists
    if check_data_exists():
        logger.info("Database already contains ferry data. Skipping initialization.")
        print("Database already contains ferry data. Skipping initialization.")
        
        # Log the successful "update" for admin panel
        with open(log_file, "a") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - Database already contains ferry data. No update needed.\n")
            
        return 0
    
    try:
        # Update the database with ferry data
        result = update_ferry_data(DEFAULT_DATA_PATH)
        logger.info(f"Database initialization completed successfully: {result}")
        print(f"Database initialization completed successfully: {result}")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}", exc_info=True)
        print(f"Error initializing database: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())