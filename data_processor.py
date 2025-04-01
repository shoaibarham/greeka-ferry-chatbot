import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from app import app
from ext import db
from models import FerryCompany, Port, Vessel, FerryRoute, Schedule, Accommodation
from config import DEFAULT_DATA_PATH

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
    with app.app_context():
        try:
            # Clear existing data (in reverse order of dependencies)
            logger.info("Clearing existing data...")
            
            # Use SQL to clear data
            db.session.execute(db.text("DELETE FROM accommodations"))
            db.session.execute(db.text("DELETE FROM schedules"))
            db.session.execute(db.text("DELETE FROM ferry_routes"))
            db.session.execute(db.text("DELETE FROM vessels"))
            db.session.execute(db.text("DELETE FROM ports"))
            db.session.execute(db.text("DELETE FROM ferry_companies"))
            db.session.commit()
            
            # Load new data
            logger.info(f"Loading ferry data from {file_path}...")
            ferry_data = load_ferry_data(file_path)
            
            # Process and store data
            logger.info("Processing ferry data...")
            process_ferry_data(ferry_data)
            
            logger.info("Ferry data update completed successfully.")
            return f"Successfully updated ferry data from {file_path}. Processed {len(ferry_data)} routes."
        
        except Exception as e:
            logger.error(f"Error updating ferry data: {str(e)}", exc_info=True)
            db.session.rollback()
            raise

def process_ferry_data(ferry_data: List[Dict[str, Any]]) -> None:
    """Process ferry data and store in database."""
    # Create dictionaries to track already processed entities
    companies = {}
    ports = {}
    vessels = {}
    routes = {}
    
    # Process each ferry route
    for route_data in ferry_data:
        # Process company
        company_code = route_data.get("company_code")
        if company_code not in companies:
            company = FerryCompany(
                code=company_code,
                name=route_data.get("company")
            )
            db.session.add(company)
            db.session.flush()  # To get the ID
            companies[company_code] = company
        else:
            company = companies[company_code]
        
        # Process origin port
        origin_code = route_data.get("origin_port_code")
        if origin_code not in ports:
            origin_port = Port(
                code=origin_code,
                name=route_data.get("origin_port")
            )
            db.session.add(origin_port)
            db.session.flush()
            ports[origin_code] = origin_port
        else:
            origin_port = ports[origin_code]
        
        # Process destination port
        dest_code = route_data.get("destination_port_code")
        if dest_code not in ports:
            dest_port = Port(
                code=dest_code,
                name=route_data.get("destination_port")
            )
            db.session.add(dest_port)
            db.session.flush()
            ports[dest_code] = dest_port
        else:
            dest_port = ports[dest_code]
        
        # Process route
        route_id = route_data.get("route_id")
        route_key = f"{route_id}_{origin_code}_{dest_code}"
        
        if route_key not in routes:
            ferry_route = FerryRoute(
                route_id=route_id,
                company_id=company.id,
                origin_port_id=origin_port.id,
                destination_port_id=dest_port.id,
                origin_port_stop=route_data.get("origin_port_stop"),
                destination_port_stop=route_data.get("destination_port_stop"),
                departure_time=route_data.get("departure_time"),
                arrival_time=route_data.get("arrival_time"),
                departure_offset=route_data.get("departure_offset"),
                arrival_offset=route_data.get("arrival_offset"),
                duration=route_data.get("duration")
            )
            db.session.add(ferry_route)
            db.session.flush()
            routes[route_key] = ferry_route
        else:
            ferry_route = routes[route_key]
        
        # Process vessels and schedules
        dates_and_vessels = route_data.get("dates_and_vessels", {})
        vessels_and_prices = route_data.get("vessels_and_indicative_prices", {})
        vessels_and_accommodation = route_data.get("vessels_and_accommodation_prices", {})
        
        for date_str, vessel_key in dates_and_vessels.items():
            # Process vessel
            if vessel_key not in vessels:
                vessel_code, vessel_name = parse_vessel_key(vessel_key)
                vessel = Vessel(
                    code=vessel_code,
                    name=vessel_name,
                    vessel_key=vessel_key
                )
                db.session.add(vessel)
                db.session.flush()
                vessels[vessel_key] = vessel
            else:
                vessel = vessels[vessel_key]
            
            # Create schedule
            indicative_price = vessels_and_prices.get(vessel_key, 0)
            schedule = Schedule(
                ferry_route_id=ferry_route.id,
                route_id=ferry_route.route_id,  # Keep original route_id for reference
                date=parse_date(date_str),
                vessel_id=vessel.id,
                indicative_price=indicative_price
            )
            db.session.add(schedule)
            
            # Process accommodations
            accommodations = vessels_and_accommodation.get(vessel_key, {})
            for acc_key, price in accommodations.items():
                if price > 0:  # Only add accommodations with prices
                    acc_code, acc_name = parse_accommodation_key(acc_key)
                    accommodation = Accommodation(
                        vessel_id=vessel.id,
                        ferry_route_id=ferry_route.id,
                        route_id=ferry_route.route_id,  # Keep original route_id for reference
                        code=acc_code,
                        name=acc_name,
                        price=price
                    )
                    db.session.add(accommodation)
        
        # Commit every 100 routes to avoid large transactions
        if len(routes) % 100 == 0:
            db.session.commit()
    
    # Final commit
    db.session.commit()
    logger.info(f"Processed {len(routes)} routes, {len(companies)} companies, {len(ports)} ports, {len(vessels)} vessels")
