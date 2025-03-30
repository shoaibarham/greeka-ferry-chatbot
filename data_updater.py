#!/usr/bin/env python3
"""
Daily data update script for the Greek Ferry information database.
This script is intended to be run daily via a scheduled task (cron job).
"""

import os
import sys
import logging
import argparse
import requests
from datetime import datetime

DEFAULT_DATA_PATH = "attached_assets/GTFS_data_v5.json"
from sqlite_loader import load_data

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("data_updates.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ferry_data_updater")

def download_data(url, output_path):
    """
    Download ferry data from the specified URL.
    
    Args:
        url: The URL to download the data from
        output_path: Where to save the downloaded data
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info(f"Downloading ferry data from {url}")
        response = requests.get(url, timeout=60)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        with open(output_path, 'wb') as f:
            f.write(response.content)
            
        logger.info(f"Data downloaded successfully to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Error downloading data: {str(e)}")
        return False

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Update ferry data in the database")
    parser.add_argument(
        "--source", 
        choices=["file", "url"], 
        default="file",
        help="Source of the data: local file or remote URL"
    )
    parser.add_argument(
        "--path", 
        default=DEFAULT_DATA_PATH,
        help="Path to the local data file or URL to download from"
    )
    parser.add_argument(
        "--download-only", 
        action="store_true",
        help="Only download the data, don't update the database"
    )
    args = parser.parse_args()
    
    # Generate timestamp for downloaded file
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    
    try:
        # Handle data source
        if args.source == "url":
            # Prepare output path for downloaded file
            output_path = f"data/ferry_data_{timestamp}.json"
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Download the data
            if not download_data(args.path, output_path):
                logger.error("Failed to download data. Aborting.")
                return 1
                
            # Update the file path to use the downloaded file
            data_path = output_path
        else:
            # Use local file
            data_path = args.path
            if not os.path.exists(data_path):
                logger.error(f"Data file not found: {data_path}")
                return 1
        
        # Update database if not download-only
        if not args.download_only:
            logger.info(f"Updating database with data from {data_path}")
            result = load_data(data_path)
            logger.info(result)
        else:
            logger.info("Download-only mode. Database not updated.")
        
        logger.info("Data update process completed successfully.")
        return 0
        
    except Exception as e:
        logger.error(f"Error in data update process: {str(e)}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())