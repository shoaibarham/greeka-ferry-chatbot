"""
Script to load ferry data from JSON file into a SQLite database.
"""

import sqlite3
import json
import os
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create a log file for data updates
log_file = "data_updates.log"
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

def create_tables(cursor):
    """
    Create the necessary tables in the SQLite database if they do not already exist.
    """
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS routes (
            route_id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_number TEXT,
            company TEXT,
            company_code TEXT,
            origin_port_code TEXT,
            origin_port_name TEXT,
            destination_port_code TEXT,
            destination_port_name TEXT,
            departure_time TEXT,
            arrival_time TEXT,
            origin_port_stop INTEGER,
            destination_port_stop INTEGER,
            departure_offset INTEGER,
            arrival_offset INTEGER,
            duration INTEGER
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dates_and_vessels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_id INTEGER,
            schedule_date TEXT,
            vessel TEXT,
            FOREIGN KEY (route_id) REFERENCES routes(route_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vessels_and_indicative_prices (
            route_id INTEGER,
            vessel TEXT,
            indicative_price INTEGER,
            PRIMARY KEY (route_id, vessel),
            FOREIGN KEY (route_id) REFERENCES routes(route_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vessels_and_accommodation_prices (
            route_id INTEGER,
            vessel TEXT,
            accommodation_type TEXT,
            price INTEGER,
            PRIMARY KEY (route_id, vessel, accommodation_type),
            FOREIGN KEY (route_id) REFERENCES routes(route_id)
        )
    ''')

def clean_text(value, to_upper=True):
    """
    Clean text values by trimming spaces, ensuring it's a string or None, 
    and optionally converting to uppercase.
    """
    if isinstance(value, str):
        value = value.strip()
        return value.upper() if to_upper else value
    return value

def insert_data(cursor, data):
    """
    Insert data into the database tables from the provided JSON data.
    """
    for item in data:
        # Insert into the routes table
        cursor.execute('''
            INSERT INTO routes (
                route_number, company, company_code, origin_port_name, origin_port_code, 
                destination_port_name, destination_port_code, departure_time, arrival_time, 
                origin_port_stop, destination_port_stop, departure_offset, arrival_offset, duration
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            clean_text(item.get('route_id')),  # Route number
            clean_text(item.get('company')),  # Company name
            clean_text(item.get('company_code')),  # Company code
            clean_text(item.get('origin_port')),  # Origin port name
            clean_text(item.get('origin_port_code')),  # Origin port code
            clean_text(item.get('destination_port')),  # Destination port name
            clean_text(item.get('destination_port_code')),  # Destination port code
            clean_text(item.get('departure_time'), to_upper=False),  # Times should remain unchanged
            clean_text(item.get('arrival_time'), to_upper=False),
            item.get('origin_port_stop'),
            item.get('destination_port_stop'),
            item.get('departure_offset'),
            item.get('arrival_offset'),
            item.get('duration')
        ))

        # Get the auto-generated ID for this route
        route_db_id = cursor.lastrowid

        # Insert into the dates_and_vessels table
        for schedule_date, vessel in item.get('dates_and_vessels', {}).items():
            cursor.execute('''
                INSERT INTO dates_and_vessels (route_id, schedule_date, vessel)
                VALUES (?, ?, ?)
            ''', (route_db_id, clean_text(schedule_date, to_upper=False), clean_text(vessel)))

        # Insert into the vessels_and_indicative_prices table
        for vessel, indicative_price in item.get('vessels_and_indicative_prices', {}).items():
            cursor.execute('''
                INSERT INTO vessels_and_indicative_prices (route_id, vessel, indicative_price)
                VALUES (?, ?, ?)
            ''', (route_db_id, clean_text(vessel), indicative_price))

        # Insert into the vessels_and_accommodation_prices table
        for vessel, accommodations in item.get('vessels_and_accommodation_prices', {}).items():
            for accommodation_type, price in accommodations.items():
                cursor.execute('''
                    INSERT INTO vessels_and_accommodation_prices (route_id, vessel, accommodation_type, price)
                    VALUES (?, ?, ?, ?)
                ''', (route_db_id, clean_text(vessel), clean_text(accommodation_type), price))

def load_data(json_path='./attached_assets/GTFS_data_v5.json', db_path='gtfs.db'):
    """
    Load data from a JSON file into the SQLite database.
    
    Args:
        json_path (str): Path to the JSON data file
        db_path (str): Path to the SQLite database
    
    Returns:
        str: Status message
    """
    try:
        logger.info(f"Loading data from {json_path} into {db_path}")
        
        # Connect to (or create) the SQLite database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create tables
        create_tables(cursor)
        
        # Clear existing data
        logger.info("Clearing existing data...")
        cursor.execute("DELETE FROM vessels_and_accommodation_prices")
        cursor.execute("DELETE FROM vessels_and_indicative_prices")
        cursor.execute("DELETE FROM dates_and_vessels")
        cursor.execute("DELETE FROM routes")

        # Load JSON data from file
        logger.info(f"Loading JSON data from {json_path}...")
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Insert data into the database
        logger.info("Inserting data into the database...")
        
        # Handle both array format and object format with 'routes' key
        if isinstance(data, list):
            # It's already in the format we want (array of routes)
            logger.info(f"Processing array format with {len(data)} routes")
            insert_data(cursor, data)
        elif isinstance(data, dict) and 'routes' in data:
            # It's in object format with 'routes' key
            logger.info(f"Processing object format with {len(data['routes'])} routes")
            insert_data(cursor, data['routes'])
        else:
            logger.error("Invalid data format: expected array or object with 'routes' key")
            conn.close()
            raise ValueError("Invalid data format: expected array or object with 'routes' key")

        # Commit the changes and close the connection
        conn.commit()
        conn.close()

        logger.info("Data loaded successfully into the database")
        
        # Write to the log file
        with open(log_file, "a") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - Data loaded successfully into {db_path}\n")
        
        return f"Data loaded successfully into {db_path}"
        
    except Exception as e:
        logger.error(f"Error loading data: {str(e)}", exc_info=True)
        return f"Error loading data: {str(e)}"

if __name__ == "__main__":
    try:
        result = load_data()
        print(result)
    except Exception as e:
        logger.error(f"Error running script: {str(e)}", exc_info=True)
        print(f"Error running script: {str(e)}")
        exit(1)
    exit(0)