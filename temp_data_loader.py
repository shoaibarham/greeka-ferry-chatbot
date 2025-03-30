"""
Temporary script to load data into the database directly using SQL.
"""

import json
import logging
import os
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

def parse_date(date_string):
    """Convert a date string to a datetime.date object."""
    return datetime.strptime(date_string, "%Y-%m-%d").date()

def parse_vessel_key(vessel_key):
    """Parse a vessel key into code and name."""
    parts = vessel_key.split("___")
    if len(parts) == 2:
        return parts[0], parts[1]
    return vessel_key, vessel_key  # Fallback

def parse_accommodation_key(accommodation_key):
    """Parse an accommodation key into code and name."""
    parts = accommodation_key.split("___")
    if len(parts) == 2:
        return parts[0], parts[1]
    return accommodation_key, accommodation_key  # Fallback

def load_data():
    """Load sample data into the database."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    import json
    
    # Get database URL from environment
    database_url = os.environ.get("DATABASE_URL", "sqlite:///ferry_data.db")
    
    # Create engine and session
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    
    # Clear database
    with Session() as session:
        logger.info("Clearing existing data...")
        session.execute(text("TRUNCATE accommodations, schedules, ferry_routes, vessels, ports, ferry_companies RESTART IDENTITY CASCADE;"))
        session.commit()
    
    # Load some sample data
    logger.info("Loading sample data...")
    
    # Create some sample data: companies, ports, vessels, routes
    
    # Insert a company
    with Session() as session:
        logger.info("Adding ferry companies...")
        session.execute(text("""
            INSERT INTO ferry_companies (code, name) VALUES
            ('SK', 'Seajets'),
            ('BF', 'Blue Ferries'),
            ('AF', 'Aegean Ferries')
        """))
        session.commit()
    
    # Insert ports
    with Session() as session:
        logger.info("Adding ports...")
        session.execute(text("""
            INSERT INTO ports (code, name) VALUES
            ('PIR', 'Piraeus'),
            ('MIL', 'Milos'),
            ('SIF', 'Sifnos'),
            ('SAN', 'Santorini'),
            ('KIM', 'Kimolos'),
            ('IOS', 'Ios'),
            ('NAX', 'Naxos'),
            ('PAR', 'Paros'),
            ('MYK', 'Mykonos')
        """))
        session.commit()
    
    # Insert vessels
    with Session() as session:
        logger.info("Adding vessels...")
        session.execute(text("""
            INSERT INTO vessels (code, name, vessel_key) VALUES
            ('WB', 'WorldChampion Jet', 'WB___WorldChampion Jet'),
            ('SJ', 'SuperJet', 'SJ___SuperJet'),
            ('CF', 'Champion Jet 1', 'CF___Champion Jet 1'),
            ('BS', 'Blue Star Delos', 'BS___Blue Star Delos'),
            ('BP', 'Blue Star Patmos', 'BP___Blue Star Patmos')
        """))
        session.commit()
    
    # Insert ferry routes
    with Session() as session:
        logger.info("Adding ferry routes...")
        session.execute(text("""
            INSERT INTO ferry_routes 
            (route_id, company_id, origin_port_id, destination_port_id, 
            origin_port_stop, destination_port_stop, departure_time, arrival_time, 
            departure_offset, arrival_offset, duration) VALUES
            
            ('101', 1, 1, 2, 1, 3, '07:30', '10:45', 0, 0, 195),
            ('102', 1, 2, 1, 3, 1, '11:15', '14:30', 0, 0, 195),
            ('103', 1, 1, 3, 1, 2, '07:30', '09:45', 0, 0, 135),
            ('104', 1, 3, 1, 2, 1, '10:15', '12:30', 0, 0, 135),
            ('105', 2, 2, 5, 1, 1, '11:00', '11:45', 0, 0, 45),
            ('106', 2, 5, 2, 1, 1, '12:15', '13:00', 0, 0, 45),
            ('107', 3, 1, 7, 1, 2, '07:30', '11:00', 0, 0, 210),
            ('108', 3, 7, 1, 2, 1, '15:30', '19:00', 0, 0, 210)
        """))
        session.commit()
    
    # Insert schedules
    with Session() as session:
        logger.info("Adding schedules...")
        session.execute(text("""
            INSERT INTO schedules (route_id, date, vessel_id, indicative_price) VALUES
            ('101', '2025-03-23', 1, 5900),
            ('101', '2025-03-24', 1, 5900),
            ('101', '2025-03-25', 1, 5900),
            ('102', '2025-03-23', 1, 5900),
            ('102', '2025-03-24', 1, 5900),
            ('102', '2025-03-25', 1, 5900),
            ('103', '2025-03-23', 2, 4900),
            ('103', '2025-03-24', 2, 4900),
            ('103', '2025-03-25', 2, 4900),
            ('104', '2025-03-23', 2, 4900),
            ('104', '2025-03-24', 2, 4900),
            ('104', '2025-03-25', 2, 4900),
            ('105', '2025-03-23', 3, 2500),
            ('105', '2025-03-24', 3, 2500),
            ('105', '2025-03-25', 3, 2500),
            ('106', '2025-03-23', 3, 2500),
            ('106', '2025-03-24', 3, 2500),
            ('106', '2025-03-25', 3, 2500),
            ('107', '2025-03-23', 4, 6900),
            ('107', '2025-03-24', 4, 6900),
            ('107', '2025-03-25', 4, 6900),
            ('108', '2025-03-23', 4, 6900),
            ('108', '2025-03-24', 4, 6900),
            ('108', '2025-03-25', 4, 6900)
        """))
        session.commit()
    
    # Insert accommodations
    with Session() as session:
        logger.info("Adding accommodations...")
        session.execute(text("""
            INSERT INTO accommodations (vessel_id, route_id, code, name, price) VALUES
            (1, '101', 'ECO', 'Economy', 5900),
            (1, '101', 'BUS', 'Business', 8900),
            (1, '101', 'VIP', 'VIP', 12900),
            (1, '102', 'ECO', 'Economy', 5900),
            (1, '102', 'BUS', 'Business', 8900),
            (1, '102', 'VIP', 'VIP', 12900),
            (2, '103', 'ECO', 'Economy', 4900),
            (2, '103', 'BUS', 'Business', 7900),
            (2, '104', 'ECO', 'Economy', 4900),
            (2, '104', 'BUS', 'Business', 7900),
            (3, '105', 'ECO', 'Economy', 2500),
            (3, '106', 'ECO', 'Economy', 2500),
            (4, '107', 'ECO', 'Economy', 6900),
            (4, '107', 'CAB', 'Cabin', 14900),
            (4, '108', 'ECO', 'Economy', 6900),
            (4, '108', 'CAB', 'Cabin', 14900)
        """))
        session.commit()
    
    # Log the update
    logger.info("Database initialized with sample data")
    
    # Write to the log file
    with open(log_file, "a") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - Database initialized with sample data\n")
    
    return "Database initialized with sample ferry data"

if __name__ == "__main__":
    try:
        result = load_data()
        print(result)
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}", exc_info=True)
        print(f"Error initializing database: {str(e)}")
        exit(1)
    exit(0)