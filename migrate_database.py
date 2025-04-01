"""
Script to migrate data from the old schema to the new schema.
This will create the new tables and move data from the old tables.
"""
import os
import logging
from datetime import datetime
from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
import json

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
DATABASE_URL = os.environ.get("DATABASE_URL")

# Create a Flask app (needed for SQLAlchemy context)
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Create SQLAlchemy engine
engine = create_engine(DATABASE_URL)
session_factory = sessionmaker(bind=engine)
db_session = scoped_session(session_factory)

def create_new_tables():
    """Create the new tables needed for the migration."""
    logger.info("Creating new database tables...")
    
    # Create routes table - using SERIAL for PostgreSQL
    db_session.execute(text("""
    CREATE TABLE IF NOT EXISTS routes (
        route_id SERIAL PRIMARY KEY,
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
    """))
    
    # Create dates_and_vessels table
    db_session.execute(text("""
    CREATE TABLE IF NOT EXISTS dates_and_vessels (
        id SERIAL PRIMARY KEY,
        route_id INTEGER,
        schedule_date TEXT,
        vessel TEXT,
        FOREIGN KEY (route_id) REFERENCES routes(route_id)
    )
    """))
    
    # Create vessels_and_indicative_prices table
    db_session.execute(text("""
    CREATE TABLE IF NOT EXISTS vessels_and_indicative_prices (
        route_id INTEGER,
        vessel TEXT,
        indicative_price INTEGER,
        PRIMARY KEY (route_id, vessel),
        FOREIGN KEY (route_id) REFERENCES routes(route_id)
    )
    """))
    
    # Create vessels_and_accommodation_prices table
    db_session.execute(text("""
    CREATE TABLE IF NOT EXISTS vessels_and_accommodation_prices (
        route_id INTEGER,
        vessel TEXT,
        accommodation_type TEXT,
        price INTEGER,
        PRIMARY KEY (route_id, vessel, accommodation_type),
        FOREIGN KEY (route_id) REFERENCES routes(route_id)
    )
    """))
    
    db_session.commit()
    logger.info("New tables created successfully")

def drop_old_tables():
    """Drop the old tables after migration."""
    logger.info("Dropping old tables...")
    
    # Drop tables in the correct order to avoid foreign key constraint issues
    db_session.execute(text("DROP TABLE IF EXISTS accommodations"))
    db_session.execute(text("DROP TABLE IF EXISTS schedules"))
    db_session.execute(text("DROP TABLE IF EXISTS ferry_routes"))
    db_session.execute(text("DROP TABLE IF EXISTS vessels"))
    db_session.execute(text("DROP TABLE IF EXISTS ports"))
    db_session.execute(text("DROP TABLE IF EXISTS ferry_companies"))
    
    db_session.commit()
    logger.info("Old tables dropped successfully")

def clear_new_tables():
    """Clear any existing data from the new tables."""
    logger.info("Clearing new tables...")
    
    # Clear tables in the correct order to avoid foreign key constraint issues
    db_session.execute(text("DELETE FROM vessels_and_accommodation_prices"))
    db_session.execute(text("DELETE FROM vessels_and_indicative_prices"))
    db_session.execute(text("DELETE FROM dates_and_vessels"))
    db_session.execute(text("DELETE FROM routes"))
    
    db_session.commit()
    logger.info("New tables cleared successfully")

def load_data_from_json(file_path):
    """Load data from a JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        logger.error(f"Failed to load data from JSON file: {e}")
        raise

def migrate_data(data):
    """Migrate data from the JSON file to the new database schema."""
    logger.info(f"Starting data migration of {len(data)} routes...")
    
    for idx, route_data in enumerate(data):
        # Clean text values
        def clean_text(value, to_upper=True):
            if isinstance(value, str):
                value = value.strip()
                return value.upper() if to_upper else value
            return value
        
        # Insert into routes table (using PostgreSQL parameter placeholders)
        result = db_session.execute(text("""
            INSERT INTO routes (
                route_number, company, company_code, origin_port_name, origin_port_code, 
                destination_port_name, destination_port_code, departure_time, arrival_time, 
                origin_port_stop, destination_port_stop, departure_offset, arrival_offset, duration
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            RETURNING route_id
        """), [
            clean_text(route_data.get('route_id')),  # Route number
            clean_text(route_data.get('company')),  # Company name
            clean_text(route_data.get('company_code')),  # Company code
            clean_text(route_data.get('origin_port')),  # Origin port name
            clean_text(route_data.get('origin_port_code')),  # Origin port code
            clean_text(route_data.get('destination_port')),  # Destination port name
            clean_text(route_data.get('destination_port_code')),  # Destination port code
            clean_text(route_data.get('departure_time'), to_upper=False),  # Times should remain unchanged
            clean_text(route_data.get('arrival_time'), to_upper=False),
            route_data.get('origin_port_stop'),
            route_data.get('destination_port_stop'),
            route_data.get('departure_offset'),
            route_data.get('arrival_offset'),
            route_data.get('duration')
        ])
        
        route_id = result.fetchone()[0]
        
        # Insert into dates_and_vessels table
        dates_and_vessels = route_data.get('dates_and_vessels', {})
        for schedule_date, vessel in dates_and_vessels.items():
            db_session.execute(text("""
                INSERT INTO dates_and_vessels (route_id, schedule_date, vessel)
                VALUES ($1, $2, $3)
            """), [
                route_id,
                clean_text(schedule_date, to_upper=False),
                clean_text(vessel)
            ])
        
        # Insert into vessels_and_indicative_prices table
        vessels_and_prices = route_data.get('vessels_and_indicative_prices', {})
        for vessel, price in vessels_and_prices.items():
            db_session.execute(text("""
                INSERT INTO vessels_and_indicative_prices (route_id, vessel, indicative_price)
                VALUES ($1, $2, $3)
            """), [
                route_id,
                clean_text(vessel),
                price
            ])
        
        # Insert into vessels_and_accommodation_prices table
        vessels_and_accommodation = route_data.get('vessels_and_accommodation_prices', {})
        for vessel, accommodations in vessels_and_accommodation.items():
            for acc_type, price in accommodations.items():
                db_session.execute(text("""
                    INSERT INTO vessels_and_accommodation_prices (route_id, vessel, accommodation_type, price)
                    VALUES ($1, $2, $3, $4)
                """), [
                    route_id,
                    clean_text(vessel),
                    clean_text(acc_type),
                    price
                ])
        
        # Commit in batches for better performance
        if idx % 100 == 0:
            db_session.commit()
            logger.info(f"Processed {idx+1} routes...")
    
    # Final commit
    db_session.commit()
    logger.info(f"Data migration completed successfully. Processed {len(data)} routes.")

def run_migration(json_file_path):
    """Run the full migration process."""
    try:
        # Step 1: Create new tables
        create_new_tables()
        
        # Step 2: Clear any existing data in new tables
        clear_new_tables()
        
        # Step 3: Load data from JSON
        data = load_data_from_json(json_file_path)
        
        # Step 4: Migrate data to new schema
        migrate_data(data)
        
        # Step 5: Drop old tables (optional, can be commented out if you want to keep them)
        drop_old_tables()
        
        logger.info("Migration completed successfully!")
        return True
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db_session.rollback()
        return False

if __name__ == "__main__":
    # Path to the JSON data file
    json_file_path = "attached_assets/GTFS_data_v5.json"
    
    # Run the migration
    success = run_migration(json_file_path)
    
    if success:
        print("Migration completed successfully!")
    else:
        print("Migration failed. Check the logs for details.")