#!/usr/bin/env python3
"""
Direct GTFS update script.
This script bypasses email fetching and directly uses a downloaded GTFS file.
"""

import os
import logging
import json
from datetime import datetime
from data_processor import update_ferry_data

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def validate_json_file(file_path):
    """Validate that a file contains valid JSON data."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, list) and len(data) > 0:
            logger.info(f"Valid JSON file with {len(data)} items")
            return True
        elif isinstance(data, dict) and 'routes' in data and len(data['routes']) > 0:
            logger.info(f"Valid JSON file with {len(data['routes'])} routes")
            return True
        else:
            logger.error(f"File does not contain expected data structure")
            return False
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON file: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error validating file: {str(e)}")
        return False

def update_using_file(file_path):
    """
    Update the database using a specific GTFS file.
    
    Args:
        file_path: Path to the GTFS JSON file
        
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info(f"Updating database with specified file: {file_path}")
    try:
        result = update_ferry_data(file_path=file_path)
        logger.info(f"Update successful: {result}")
        return True
    except Exception as e:
        logger.error(f"Error updating database: {str(e)}")
        return False

def main():
    """Update the database using the latest downloaded GTFS file."""
    # Path to the GTFS updates directory
    updates_dir = 'gtfs_updates'
    
    logger.info("Starting direct GTFS update...")
    
    # Make sure the updates directory exists
    if not os.path.exists(updates_dir):
        logger.error(f"Updates directory {updates_dir} does not exist")
        return False
    
    # Get all JSON files in the updates directory
    json_files = [f for f in os.listdir(updates_dir) if f.endswith('.json')]
    
    if not json_files:
        logger.error("No JSON files found in updates directory")
        return False
    
    # Find the newest valid JSON file
    valid_files = []
    for filename in json_files:
        file_path = os.path.join(updates_dir, filename)
        if validate_json_file(file_path):
            valid_files.append((file_path, os.path.getmtime(file_path)))
    
    if not valid_files:
        logger.error("No valid JSON files found")
        return False
    
    # Sort by modification time, newest first
    valid_files.sort(key=lambda x: x[1], reverse=True)
    newest_file = valid_files[0][0]
    
    # Update the database
    return update_using_file(newest_file)

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)