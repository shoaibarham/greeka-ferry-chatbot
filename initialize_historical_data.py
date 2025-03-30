"""
Initialize historical ferry database with data from the provided JSON file.
This script should be run once to populate the historical database.
"""

import logging
import os
from historical_data_loader import load_historical_data

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_data_exists():
    """Check if there is already data in the historical database."""
    import sqlite3
    
    if not os.path.exists('previous_db.db'):
        logger.info("Historical database file doesn't exist yet.")
        return False
    
    conn = sqlite3.connect('previous_db.db')
    cursor = conn.cursor()
    
    # Check if the historical_date_ranges table exists and has data
    try:
        cursor.execute("SELECT COUNT(*) FROM historical_date_ranges")
        count = cursor.fetchone()[0]
        conn.close()
        
        logger.info(f"Found {count} records in historical_date_ranges table.")
        return count > 0
    except sqlite3.OperationalError:
        # Table doesn't exist
        conn.close()
        logger.info("historical_date_ranges table doesn't exist yet.")
        return False

def main():
    """Initialize the historical database with ferry data."""
    logger.info("Starting historical database initialization...")
    
    # Check if historical data already exists
    if check_data_exists():
        logger.info("Historical database already contains data. Skipping initialization.")
        return "Historical database already initialized."
    
    # Load data from the JSON file into the database
    result = load_historical_data(
        json_path='./attached_assets/GTFS appear dates.json',
        db_path='previous_db.db'
    )
    
    logger.info(f"Database initialization complete: {result}")
    return result

if __name__ == "__main__":
    try:
        result = main()
        print(result)
    except Exception as e:
        logger.error(f"Error initializing historical database: {str(e)}", exc_info=True)
        print(f"Error initializing historical database: {str(e)}")
        exit(1)
    exit(0)