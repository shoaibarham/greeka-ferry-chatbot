import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)

def format_price(price_cents: int) -> str:
    """Format price from cents to euros with 2 decimal places."""
    return f"€{price_cents/100:.2f}"

def parse_time(time_str: str) -> datetime.time:
    """Parse a time string in HH:MM format."""
    hour, minute = map(int, time_str.split(':'))
    return datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()

def calculate_travel_time(duration_minutes: int) -> str:
    """Convert duration in minutes to a readable format."""
    hours, minutes = divmod(duration_minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
    return f"{minutes}m"

def format_schedule_response(route_data: Dict[str, Any]) -> Dict[str, Any]:
    """Format route data for response."""
    return {
        "origin": route_data.get("origin_port_name"),
        "destination": route_data.get("destination_port_name"),
        "date": route_data.get("date"),
        "departure_time": route_data.get("departure_time"),
        "arrival_time": route_data.get("arrival_time"),
        "duration": calculate_travel_time(route_data.get("duration", 0)),
        "company": route_data.get("company_name"),
        "vessel": route_data.get("vessel_name"),
        "base_price": format_price(route_data.get("indicative_price", 0)),
        "accommodations": [
            {
                "type": acc.get("name"),
                "price": format_price(acc.get("price", 0))
            } for acc in route_data.get("accommodations", [])
        ]
    }

def extract_date_from_text(text: str) -> Optional[str]:
    """
    Extract date from natural language text.
    Supports formats like 'March 23, 2025', '23/03/2025', '2025-03-23', etc.
    """
    # Try different date patterns
    patterns = [
        r'(\d{4}-\d{1,2}-\d{1,2})',  # YYYY-MM-DD
        r'(\d{1,2}/\d{1,2}/\d{4})',  # DD/MM/YYYY
        r'(\d{1,2}-\d{1,2}-\d{4})',  # DD-MM-YYYY
        r'(\w+ \d{1,2},? \d{4})'     # Month DD, YYYY
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(1)
            try:
                # Try parsing with different formats
                for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%B %d, %Y', '%B %d %Y'):
                    try:
                        date_obj = datetime.strptime(date_str, fmt)
                        return date_obj.strftime('%Y-%m-%d')
                    except ValueError:
                        continue
            except Exception as e:
                logger.error(f"Error parsing date {date_str}: {str(e)}")
    
    # Check for relative dates
    relative_patterns = {
        r'today': 0,
        r'tomorrow': 1,
        r'day after tomorrow': 2,
        r'next week': 7
    }
    
    for pattern, days in relative_patterns.items():
        if re.search(pattern, text.lower()):
            date_obj = datetime.now() + timedelta(days=days)
            return date_obj.strftime('%Y-%m-%d')
    
    return None

def extract_ports_from_text(text: str, ports_list: List[Dict[str, str]]) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract origin and destination ports from text based on available ports.
    
    Args:
        text: The user's query text
        ports_list: List of port dictionaries with 'code' and 'name' keys
    
    Returns:
        Tuple of (origin_code, destination_code)
    """
    port_names = {port['name'].lower(): port['code'] for port in ports_list}
    port_codes = {port['code'].lower(): port['code'] for port in ports_list}
    
    # Combined map for lookup
    port_map = {**port_names, **port_codes}
    
    # Common prepositions indicating origin/destination
    origin_indicators = ['from', 'starting at', 'departing from', 'leaving from']
    dest_indicators = ['to', 'going to', 'arriving at', 'arriving in', 'destination']
    
    origin = None
    destination = None
    
    # Check for ports by name or code
    words = text.lower().split()
    for port_name, port_code in port_map.items():
        if port_name in text.lower():
            # Determine if it's origin or destination based on position and context
            port_pos = text.lower().find(port_name)
            
            # Check for origin indicators
            is_origin = any(ind in text.lower()[:port_pos] for ind in origin_indicators)
            
            # Check for destination indicators
            is_dest = any(ind in text.lower()[:port_pos] for ind in dest_indicators)
            
            if is_origin and not origin:
                origin = port_code
            elif is_dest and not destination:
                destination = port_code
            elif not origin:
                origin = port_code
            elif not destination:
                destination = port_code
    
    # If we identified both, return them
    if origin and destination:
        return origin, destination
    
    # If we only found one, try to infer the other from common patterns
    if origin and not destination:
        # Look for words after "to"
        to_index = text.lower().find(" to ")
        if to_index > 0:
            after_to = text[to_index+4:].split()
            for word in after_to:
                word = word.lower().strip(".,?!")
                if word in port_map:
                    destination = port_map[word]
                    break
    
    if destination and not origin:
        # Look for words after "from"
        from_index = text.lower().find(" from ")
        if from_index > 0:
            after_from = text[from_index+6:].split()
            for word in after_from:
                word = word.lower().strip(".,?!")
                if word in port_map:
                    origin = port_map[word]
                    break
    
    return origin, destination
