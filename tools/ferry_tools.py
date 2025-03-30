import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

from langchain.tools import BaseTool, StructuredTool, tool
from db import execute_query
from utils import (
    format_price, extract_date_from_text, extract_ports_from_text, 
    format_schedule_response
)

logger = logging.getLogger(__name__)

class PortInfo(BaseModel):
    """Information about a port."""
    code: str = Field(..., description="The port code")
    name: str = Field(..., description="The name of the port")

class FerrySearchParams(BaseModel):
    """Parameters for searching ferry routes."""
    origin: str = Field(..., description="The origin port code")
    destination: str = Field(..., description="The destination port code")
    date: str = Field(..., description="The departure date in YYYY-MM-DD format")

class MultiSegmentParams(BaseModel):
    """Parameters for searching multi-segment routes."""
    origin: str = Field(..., description="The origin port code")
    destination: str = Field(..., description="The final destination port code")
    intermediate_stop: str = Field(..., description="The intermediate port code")
    date: str = Field(..., description="The departure date in YYYY-MM-DD format")

@tool
def get_all_ports() -> List[Dict[str, str]]:
    """
    Get a list of all available ports.
    Returns a list of dictionaries with port code and name.
    """
    try:
        query = """
        SELECT code, name FROM ports
        ORDER BY name
        """
        results = execute_query(query)
        return [{"code": row[0], "name": row[1]} for row in results]
    except Exception as e:
        logger.error(f"Error in get_all_ports: {str(e)}")
        return []

@tool
def extract_query_parameters(query: str) -> Dict[str, Any]:
    """
    Extract ferry search parameters from the user query.
    
    Args:
        query: The user's natural language query
        
    Returns:
        Dictionary with extracted origin, destination, and date
    """
    try:
        # Get the list of ports to help with extraction
        ports = get_all_ports()
        
        # Extract date
        date = extract_date_from_text(query)
        if not date:
            # Default to today if no date found
            date = datetime.now().strftime('%Y-%m-%d')
        
        # Extract origin and destination ports
        origin, destination = extract_ports_from_text(query, ports)
        
        return {
            "origin": origin,
            "destination": destination,
            "date": date
        }
    except Exception as e:
        logger.error(f"Error in extract_query_parameters: {str(e)}")
        return {"origin": None, "destination": None, "date": None}

@tool
def search_ferry_routes(params: FerrySearchParams) -> List[Dict[str, Any]]:
    """
    Search for ferry routes between origin and destination on a specific date.
    
    Args:
        params: FerrySearchParams containing origin, destination, and date
        
    Returns:
        List of matching ferry routes with schedule and pricing information
    """
    try:
        query = """
        SELECT
            fr.route_id,
            orig.code as origin_code,
            orig.name as origin_name,
            dest.code as destination_code,
            dest.name as destination_name,
            fr.departure_time,
            fr.arrival_time,
            fr.duration,
            fc.name as company_name,
            fc.code as company_code,
            v.name as vessel_name,
            s.date,
            s.indicative_price
        FROM
            ferry_routes fr
        JOIN
            ferry_companies fc ON fr.company_id = fc.id
        JOIN
            ports orig ON fr.origin_port_id = orig.id
        JOIN
            ports dest ON fr.destination_port_id = dest.id
        JOIN
            schedules s ON fr.route_id = s.route_id
        JOIN
            vessels v ON s.vessel_id = v.id
        WHERE
            orig.code = :origin
            AND dest.code = :destination
            AND s.date = :date
        ORDER BY
            fr.departure_time
        """
        
        results = execute_query(query, {
            "origin": params.origin,
            "destination": params.destination,
            "date": params.date
        })
        
        routes = []
        for row in results:
            route_data = {
                "route_id": row[0],
                "origin_code": row[1],
                "origin_port_name": row[2],
                "destination_code": row[3],
                "destination_port_name": row[4],
                "departure_time": row[5],
                "arrival_time": row[6],
                "duration": row[7],
                "company_name": row[8],
                "company_code": row[9],
                "vessel_name": row[10],
                "date": row[11].strftime('%Y-%m-%d'),
                "indicative_price": row[12]
            }
            
            # Get accommodation options
            acc_query = """
            SELECT
                a.code,
                a.name,
                a.price
            FROM
                accommodations a
            JOIN
                vessels v ON a.vessel_id = v.id
            WHERE
                a.route_id = :route_id
                AND v.name = :vessel_name
            """
            
            acc_results = execute_query(acc_query, {
                "route_id": route_data["route_id"],
                "vessel_name": route_data["vessel_name"]
            })
            
            route_data["accommodations"] = [
                {"code": row[0], "name": row[1], "price": row[2]}
                for row in acc_results
            ]
            
            routes.append(format_schedule_response(route_data))
        
        return routes
    except Exception as e:
        logger.error(f"Error in search_ferry_routes: {str(e)}")
        return []

@tool
def get_cheapest_route(params: FerrySearchParams) -> Optional[Dict[str, Any]]:
    """
    Find the cheapest ferry route between origin and destination on a specific date.
    
    Args:
        params: FerrySearchParams containing origin, destination, and date
        
    Returns:
        The cheapest ferry route or None if no routes found
    """
    try:
        routes = search_ferry_routes(params)
        if not routes:
            return None
        
        # Sort by price and return the cheapest
        return min(routes, key=lambda x: float(x["base_price"].replace("€", "")))
    except Exception as e:
        logger.error(f"Error in get_cheapest_route: {str(e)}")
        return None

@tool
def get_fastest_route(params: FerrySearchParams) -> Optional[Dict[str, Any]]:
    """
    Find the fastest ferry route between origin and destination on a specific date.
    
    Args:
        params: FerrySearchParams containing origin, destination, and date
        
    Returns:
        The fastest ferry route or None if no routes found
    """
    try:
        # Get all routes
        query = """
        SELECT
            fr.route_id,
            orig.code as origin_code,
            orig.name as origin_name,
            dest.code as destination_code,
            dest.name as destination_name,
            fr.departure_time,
            fr.arrival_time,
            fr.duration,
            fc.name as company_name,
            fc.code as company_code,
            v.name as vessel_name,
            s.date,
            s.indicative_price
        FROM
            ferry_routes fr
        JOIN
            ferry_companies fc ON fr.company_id = fc.id
        JOIN
            ports orig ON fr.origin_port_id = orig.id
        JOIN
            ports dest ON fr.destination_port_id = dest.id
        JOIN
            schedules s ON fr.route_id = s.route_id
        JOIN
            vessels v ON s.vessel_id = v.id
        WHERE
            orig.code = :origin
            AND dest.code = :destination
            AND s.date = :date
        ORDER BY
            fr.duration ASC
        LIMIT 1
        """
        
        results = execute_query(query, {
            "origin": params.origin,
            "destination": params.destination,
            "date": params.date
        })
        
        if not results:
            return None
            
        row = results[0]
        route_data = {
            "route_id": row[0],
            "origin_code": row[1],
            "origin_port_name": row[2],
            "destination_code": row[3],
            "destination_port_name": row[4],
            "departure_time": row[5],
            "arrival_time": row[6],
            "duration": row[7],
            "company_name": row[8],
            "company_code": row[9],
            "vessel_name": row[10],
            "date": row[11].strftime('%Y-%m-%d'),
            "indicative_price": row[12]
        }
        
        # Get accommodation options
        acc_query = """
        SELECT
            a.code,
            a.name,
            a.price
        FROM
            accommodations a
        JOIN
            vessels v ON a.vessel_id = v.id
        WHERE
            a.route_id = :route_id
            AND v.name = :vessel_name
        """
        
        acc_results = execute_query(acc_query, {
            "route_id": route_data["route_id"],
            "vessel_name": route_data["vessel_name"]
        })
        
        route_data["accommodations"] = [
            {"code": row[0], "name": row[1], "price": row[2]}
            for row in acc_results
        ]
        
        return format_schedule_response(route_data)
    except Exception as e:
        logger.error(f"Error in get_fastest_route: {str(e)}")
        return None

@tool
def find_multi_segment_route(params: MultiSegmentParams) -> List[Dict[str, Any]]:
    """
    Find a multi-segment route with an intermediate stop.
    
    Args:
        params: MultiSegmentParams containing origin, destination, intermediate_stop, and date
        
    Returns:
        List of ferry routes forming a multi-segment journey
    """
    try:
        # First segment: origin to intermediate
        first_segment_params = FerrySearchParams(
            origin=params.origin,
            destination=params.intermediate_stop,
            date=params.date
        )
        first_segment = search_ferry_routes(first_segment_params)
        
        if not first_segment:
            return []
        
        # Get the arrival date/time of the first segment to use for the second segment
        first_arrival_date = params.date  # Assume same day for simplicity
        
        # Second segment: intermediate to destination
        second_segment_params = FerrySearchParams(
            origin=params.intermediate_stop,
            destination=params.destination,
            date=first_arrival_date
        )
        second_segment = search_ferry_routes(second_segment_params)
        
        if not second_segment:
            return []
        
        # Check if the connection is possible (enough time between segments)
        valid_connections = []
        for first in first_segment:
            first_arrival = first["arrival_time"]
            
            for second in second_segment:
                second_departure = second["departure_time"]
                
                # Simple time string comparison (assuming HH:MM format)
                if second_departure > first_arrival:
                    valid_connections.append({
                        "first_segment": first,
                        "second_segment": second,
                        "total_duration": f"Combined duration: {first['duration']} + {second['duration']}",
                        "connection_time": f"Connection time: (arrive {first_arrival} → depart {second_departure})",
                        "total_price": f"Total price: {format_price(int(float(first['base_price'].replace('€', '')) * 100) + int(float(second['base_price'].replace('€', '')) * 100))}"
                    })
        
        return valid_connections
    except Exception as e:
        logger.error(f"Error in find_multi_segment_route: {str(e)}")
        return []

@tool
def get_available_dates(origin: str, destination: str) -> List[str]:
    """
    Get all available dates for a specific origin-destination pair.
    
    Args:
        origin: The origin port code
        destination: The destination port code
        
    Returns:
        List of dates (YYYY-MM-DD format) when ferries operate on this route
    """
    try:
        query = """
        SELECT DISTINCT
            s.date
        FROM
            ferry_routes fr
        JOIN
            ports orig ON fr.origin_port_id = orig.id
        JOIN
            ports dest ON fr.destination_port_id = dest.id
        JOIN
            schedules s ON fr.route_id = s.route_id
        WHERE
            orig.code = :origin
            AND dest.code = :destination
            AND s.date >= CURRENT_DATE
        ORDER BY
            s.date
        """
        
        results = execute_query(query, {"origin": origin, "destination": destination})
        return [row[0].strftime('%Y-%m-%d') for row in results]
    except Exception as e:
        logger.error(f"Error in get_available_dates: {str(e)}")
        return []

@tool
def get_available_accommodations(route_id: str, vessel_name: str) -> List[Dict[str, Any]]:
    """
    Get all available accommodation types for a specific route and vessel.
    
    Args:
        route_id: The route ID
        vessel_name: The vessel name
        
    Returns:
        List of accommodation types with prices
    """
    try:
        query = """
        SELECT
            a.code,
            a.name,
            a.price
        FROM
            accommodations a
        JOIN
            vessels v ON a.vessel_id = v.id
        WHERE
            a.route_id = :route_id
            AND v.name = :vessel_name
        ORDER BY
            a.price
        """
        
        results = execute_query(query, {"route_id": route_id, "vessel_name": vessel_name})
        return [
            {
                "code": row[0],
                "name": row[1],
                "price": format_price(row[2])
            }
            for row in results
        ]
    except Exception as e:
        logger.error(f"Error in get_available_accommodations: {str(e)}")
        return []

def get_tools():
    """Return all the tools available for the ferry chatbot."""
    return [
        get_all_ports,
        extract_query_parameters,
        search_ferry_routes,
        get_cheapest_route,
        get_fastest_route,
        find_multi_segment_route,
        get_available_dates,
        get_available_accommodations
    ]
