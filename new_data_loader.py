"""
Data loader for updating ferry information in the database using our new schema.
"""
import os
import logging
import json
from datetime import datetime

from ext import db
from new_models import Route, DateAndVessel, VesselIndicativePrice, VesselAccommodationPrice

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   filename='data_updates.log')
logger = logging.getLogger(__name__)

DEFAULT_DATA_PATH = "attached_assets/GTFS_data_v5.json"

def load_ferry_data(file_path=DEFAULT_DATA_PATH):
    """
    Load ferry data from JSON file.
    
    Args:
        file_path (str): Path to the JSON data file
        
    Returns:
        list: List of ferry route data dicts
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"Successfully loaded {len(data)} ferry routes from {file_path}")
        return data
    except Exception as e:
        logger.error(f"Failed to load ferry data: {e}")
        raise

def update_ferry_data(file_path=DEFAULT_DATA_PATH):
    """
    Update the database with the latest ferry data.
    This function will clear existing data and reload from the specified file.
    
    Args:
        file_path (str): Path to the JSON data file
        
    Returns:
        str: Status message
    """
    try:
        # Load data from file
        data = load_ferry_data(file_path)
        
        # Start a transaction
        logger.info("Starting database update transaction")
        
        # Clear existing data
        VesselAccommodationPrice.query.delete()
        VesselIndicativePrice.query.delete()
        DateAndVessel.query.delete()
        Route.query.delete()
        
        logger.info("Cleared existing data, starting import")
        
        # Process and insert the data
        process_ferry_data(data)
        
        # Commit the transaction
        db.session.commit()
        
        message = f"Successfully updated ferry data. {len(data)} routes processed."
        logger.info(message)
        return message
    
    except Exception as e:
        # Rollback the transaction in case of error
        db.session.rollback()
        error_message = f"Failed to update ferry data: {str(e)}"
        logger.error(error_message)
        return error_message

def process_ferry_data(ferry_data):
    """
    Process ferry data and store in database.
    
    Args:
        ferry_data (list): List of ferry route data dicts
    """
    routes_added = 0
    schedules_added = 0
    prices_added = 0
    accommodations_added = 0
    
    for route_data in ferry_data:
        try:
            # Create a new route record
            route = Route(
                route_number=route_data.get('route_id', ''),
                company=route_data.get('company', '').upper(),
                company_code=route_data.get('company_code', '').upper(),
                origin_port_code=route_data.get('origin_port_code', '').upper(),
                origin_port_name=route_data.get('origin_port', '').upper(),
                destination_port_code=route_data.get('destination_port_code', '').upper(),
                destination_port_name=route_data.get('destination_port', '').upper(),
                departure_time=route_data.get('departure_time', ''),
                arrival_time=route_data.get('arrival_time', ''),
                origin_port_stop=route_data.get('origin_port_stop', 0),
                destination_port_stop=route_data.get('destination_port_stop', 0),
                departure_offset=route_data.get('departure_offset', 0),
                arrival_offset=route_data.get('arrival_offset', 0),
                duration=route_data.get('duration', 0)
            )
            
            db.session.add(route)
            # Need to flush to get the route_id
            db.session.flush()
            routes_added += 1
            
            # Process schedules
            dates_and_vessels = route_data.get('dates_and_vessels', {})
            for schedule_date, vessel in dates_and_vessels.items():
                try:
                    date_obj = datetime.strptime(schedule_date, '%Y-%m-%d').date()
                    schedule = DateAndVessel(
                        route_id=route.route_id,
                        schedule_date=date_obj,
                        vessel=vessel.upper()
                    )
                    db.session.add(schedule)
                    schedules_added += 1
                except Exception as e:
                    logger.warning(f"Error processing schedule {schedule_date} for route {route.route_id}: {e}")
            
            # Process indicative prices
            vessels_and_prices = route_data.get('vessels_and_indicative_prices', {})
            for vessel, price in vessels_and_prices.items():
                try:
                    indicative_price = VesselIndicativePrice(
                        route_id=route.route_id,
                        vessel=vessel.upper(),
                        indicative_price=price
                    )
                    db.session.add(indicative_price)
                    prices_added += 1
                except Exception as e:
                    logger.warning(f"Error processing indicative price for vessel {vessel} on route {route.route_id}: {e}")
            
            # Process accommodation prices
            vessels_and_accommodations = route_data.get('vessels_and_accommodation_prices', {})
            for vessel, accommodations in vessels_and_accommodations.items():
                for acc_type, price in accommodations.items():
                    try:
                        accommodation_price = VesselAccommodationPrice(
                            route_id=route.route_id,
                            vessel=vessel.upper(),
                            accommodation_type=acc_type.upper(),
                            price=price
                        )
                        db.session.add(accommodation_price)
                        accommodations_added += 1
                    except Exception as e:
                        logger.warning(f"Error processing accommodation price for {acc_type} on vessel {vessel}, route {route.route_id}: {e}")
            
            # Flush periodically to avoid excessive memory usage
            if routes_added % 100 == 0:
                db.session.flush()
                logger.info(f"Processed {routes_added} routes so far")
                
        except Exception as e:
            logger.error(f"Error processing route {route_data.get('route_id')}: {e}")
            # Continue processing other routes
    
    logger.info(f"Added {routes_added} routes, {schedules_added} schedules, {prices_added} indicative prices, and {accommodations_added} accommodation prices")

if __name__ == "__main__":
    # This allows running the script directly to update data
    update_ferry_data()