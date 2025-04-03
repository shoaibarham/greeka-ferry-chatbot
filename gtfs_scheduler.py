"""
GTFS Data Scheduler.
This module handles scheduling and execution of GTFS data updates.
"""

import os
import json
import logging
import time
import signal
import sys
from datetime import datetime, timedelta
import pytz
import threading
import schedule
from email_fetcher import EmailFetcher
from data_processor import update_ferry_data
from historical_data_loader import load_historical_data

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='data_updates.log'
)

logger = logging.getLogger(__name__)

# Greek timezone
GREEK_TZ = pytz.timezone('Europe/Athens')

class GTFSScheduler:
    """
    Scheduler for GTFS data updates from email.
    """
    def __init__(self, config_path="gtfs_scheduler_config.json"):
        """
        Initialize the GTFS scheduler.
        
        Args:
            config_path: Path to the configuration file
        """
        self.config_path = config_path
        self.config = self._load_config()
        
        # Initialize with hardcoded Gmail credentials 
        # This is a workaround for persistent environment variable issues
        self.email_fetcher = EmailFetcher(
            email_address="arhammuhammadshoaib@gmail.com",
            password="peutrhospmfmftr",  # App Password with spaces removed
            imap_server="imap.gmail.com",
            imap_port=993
        )
        
        self.running = False
        self.thread = None
        
        # Configure the scheduler with defaults if not found in config
        self.update_time = self.config.get('update_time', '03:00')  # 3 AM by default
        self.update_days = self.config.get('update_days', ['monday', 'wednesday', 'friday'])
        self.email_filter = self.config.get('email_filter', {'subject': 'GTFS', 'days_back': 7})
        self.update_directory = self.config.get('update_directory', './gtfs_updates')
        self.enable_historical = self.config.get('enable_historical', True)
        
        # Ensure update directory exists
        os.makedirs(self.update_directory, exist_ok=True)
    
    def _load_config(self):
        """
        Load scheduler configuration from file.
        
        Returns:
            dict: Configuration dictionary
        """
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            else:
                # Create default config
                default_config = {
                    'update_time': '03:00',  # 3 AM by default in Greek time
                    'update_days': ['monday', 'wednesday', 'friday'], 
                    'email_filter': {
                        'subject': 'GTFS',
                        'sender': None,  # any sender
                        'days_back': 7
                    },
                    'update_directory': './gtfs_updates',
                    'enable_historical': True,
                    'email_credentials': {
                        'use_env_vars': True,  # Use env vars for credentials by default
                        'email': None,
                        'password': None,
                        'server': 'imap.gmail.com',
                        'port': 993
                    }
                }
                
                # Save default config
                with open(self.config_path, 'w') as f:
                    json.dump(default_config, f, indent=4)
                    
                logger.info(f"Created default config at {self.config_path}")
                return default_config
                
        except Exception as e:
            logger.error(f"Error loading config: {str(e)}")
            return {}
    
    def save_config(self):
        """
        Save current configuration to file.
        """
        try:
            # Don't save sensitive information to the config file
            safe_config = self.config.copy()
            if 'email_credentials' in safe_config:
                safe_config['email_credentials'] = {
                    **safe_config['email_credentials'],
                    'email': None if safe_config['email_credentials'].get('use_env_vars') else safe_config['email_credentials'].get('email'),
                    'password': None  # Never save password to disk
                }
            
            with open(self.config_path, 'w') as f:
                json.dump(safe_config, f, indent=4)
                
            logger.info(f"Configuration saved to {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving config: {str(e)}")
            return False
    
    def update_config(self, update_dict):
        """
        Update scheduler configuration.
        
        Args:
            update_dict: Dictionary containing config updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            for key, value in update_dict.items():
                if key in self.config:
                    if isinstance(self.config[key], dict) and isinstance(value, dict):
                        self.config[key].update(value)
                    else:
                        self.config[key] = value
                else:
                    self.config[key] = value
            
            # Update instance variables if relevant
            if 'update_time' in update_dict:
                self.update_time = update_dict['update_time']
            if 'update_days' in update_dict:
                self.update_days = update_dict['update_days']
            if 'email_filter' in update_dict:
                self.email_filter = update_dict['email_filter']
            if 'update_directory' in update_dict:
                self.update_directory = update_dict['update_directory']
                os.makedirs(self.update_directory, exist_ok=True)
            if 'enable_historical' in update_dict:
                self.enable_historical = update_dict['enable_historical']
            
            # Save updated config
            return self.save_config()
        except Exception as e:
            logger.error(f"Error updating config: {str(e)}")
            return False
    
    def configure_email_credentials(self, email=None, password=None, use_env_vars=None):
        """
        Configure the email credentials.
        
        Args:
            email: Email address to use
            password: Email password to use
            use_env_vars: Whether to use environment variables for credentials
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Always use hardcoded Gmail credentials regardless of inputs
            # This is a workaround for persistent environment variable issues
            hardcoded_email = "arhammuhammadshoaib@gmail.com"
            hardcoded_password = "peutrhospmfmftr"  # App Password with spaces removed
            
            # Set credentials in the email fetcher
            self.email_fetcher.set_credentials(hardcoded_email, hardcoded_password)
            logger.info(f"Using hardcoded Gmail credentials ({hardcoded_email}) for consistent operation")
            
            # Update config for UI consistency, but actual operation will use hardcoded values
            if 'email_credentials' not in self.config:
                self.config['email_credentials'] = {}
            
            if use_env_vars is not None:
                self.config['email_credentials']['use_env_vars'] = use_env_vars
            
            if not use_env_vars and email:
                self.config['email_credentials']['email'] = email
            
            # Save config (will save safely without password)
            return self.save_config()
        except Exception as e:
            logger.error(f"Error configuring email credentials: {str(e)}")
            return False
    
    def check_and_update_gtfs(self):
        """
        Check for new GTFS data and update the database if found.
        
        Returns:
            bool: True if update was performed, False otherwise
        """
        try:
            logger.info("Starting GTFS data update check")
            
            # For consistent operation, always override with Gmail credentials
            self.email_fetcher.set_credentials(
                "arhammuhammadshoaib@gmail.com", 
                "peutrhospmfmftr"  # App Password with spaces removed
            )
            
            # Connect to email
            if not self.email_fetcher.connect():
                logger.error("Failed to connect to email server")
                return False
            
            # Fetch recent GTFS data
            days_back = self.email_filter.get('days_back', 7)
            subject = self.email_filter.get('subject', 'GTFS')
            sender = self.email_filter.get('sender')
            
            logger.info(f"Searching for emails with subject '{subject}' from the last {days_back} days")
            
            # Search for matching emails
            since_date = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            since_date = since_date.replace(day=since_date.day - days_back)
            
            email_ids = self.email_fetcher.search_emails(
                subject_filter=subject,
                sender_filter=sender,
                since_date=since_date
            )
            
            if not email_ids:
                logger.info(f"No matching emails found")
                self.email_fetcher.disconnect()
                return False
            
            # Process each email and download attachments
            all_attachments = []
            for email_id in email_ids:
                attachments = self.email_fetcher.fetch_attachments(
                    email_id, 
                    save_dir=self.update_directory
                )
                all_attachments.extend(attachments)
            
            # Disconnect from email
            self.email_fetcher.disconnect()
            
            if not all_attachments:
                logger.info("No GTFS attachments found in emails")
                return False
            
            # Find the newest valid GTFS file
            newest_file = None
            newest_time = None
            
            for file_path in all_attachments:
                if not self.email_fetcher.validate_gtfs_json(file_path):
                    continue
                
                file_time = os.path.getmtime(file_path)
                if newest_time is None or file_time > newest_time:
                    newest_time = file_time
                    newest_file = file_path
            
            if not newest_file:
                logger.warning("No valid GTFS files found in attachments")
                return False
            
            # Update the ferry data
            logger.info(f"Updating ferry data with file: {newest_file}")
            update_result = update_ferry_data(file_path=newest_file)
            
            # Update historical data if enabled
            if self.enable_historical:
                historical_file = os.path.join(os.path.dirname(newest_file), "historical_data.json")
                
                # Check if there's a historical data file with similar name
                base_name = os.path.basename(newest_file)
                base_name = base_name.split('_', 1)[1] if '_' in base_name else base_name
                base_name = os.path.splitext(base_name)[0]
                
                possible_historical_files = [
                    f for f in all_attachments 
                    if "historical" in f.lower() and base_name in f
                ]
                
                if possible_historical_files:
                    historical_file = possible_historical_files[0]
                    logger.info(f"Found matching historical data file: {historical_file}")
                    
                    if os.path.exists(historical_file):
                        logger.info(f"Updating historical data with file: {historical_file}")
                        load_historical_data(historical_file)
            
            logger.info("GTFS data update completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error in check_and_update_gtfs: {str(e)}")
            return False
    
    def _schedule_tasks(self):
        """
        Configure scheduled tasks.
        """
        # Clear existing schedules
        schedule.clear()
        
        # Schedule updates for configured days at the specified time
        for day in self.update_days:
            getattr(schedule.every(), day.lower()).at(self.update_time).do(self.check_and_update_gtfs)
            
        logger.info(f"Scheduled updates for {', '.join(self.update_days)} at {self.update_time} (Greek time)")
    
    def _run_scheduler(self):
        """
        Run the scheduler loop.
        """
        self._schedule_tasks()
        
        logger.info("Scheduler started")
        
        while self.running:
            # Convert current time to Greek time
            now = datetime.now(pytz.utc).astimezone(GREEK_TZ)
            logger.debug(f"Current time (Greek): {now.strftime('%Y-%m-%d %H:%M:%S')}")
            
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    def start(self):
        """
        Start the scheduler in a background thread.
        """
        if self.running:
            logger.warning("Scheduler is already running")
            return False
        
        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler)
        self.thread.daemon = True
        self.thread.start()
        
        logger.info("GTFS scheduler started")
        return True
    
    def stop(self):
        """
        Stop the scheduler.
        """
        if not self.running:
            logger.warning("Scheduler is not running")
            return False
        
        logger.info("Stopping GTFS scheduler...")
        self.running = False
        
        if self.thread:
            self.thread.join(timeout=5)
            
        logger.info("GTFS scheduler stopped")
        return True
    
    def run_update_now(self):
        """
        Run an update immediately.
        
        Returns:
            bool: True if update was successful, False otherwise
        """
        logger.info("Running GTFS update now")
        
        # HARDCODED OVERRIDE - Set Gmail credentials directly
        # This is a workaround for persistent environment variable issues
        self.email_fetcher.set_credentials(
            "arhammuhammadshoaib@gmail.com", 
            "peutrhospmfmftr"  # App Password with spaces removed
        )
        logger.info("Using Gmail credentials for manual update")
        
        return self.check_and_update_gtfs()
    
    def get_next_update_time(self):
        """
        Get the next scheduled update time in Greek timezone.
        
        Returns:
            str: Next update time or "Not scheduled" if no schedule
        """
        try:
            next_run = schedule.next_run()
            if next_run:
                # Convert to Greek time
                next_run_greek = pytz.utc.localize(next_run).astimezone(GREEK_TZ)
                return next_run_greek.strftime("%Y-%m-%d %H:%M:%S (Greek time)")
            return "Not scheduled"
        except Exception:
            return "Not scheduled"


def run_scheduler():
    """
    Run the GTFS scheduler as a daemon.
    """
    scheduler = GTFSScheduler()
    
    # Handle signals for graceful shutdown
    def signal_handler(sig, frame):
        print("Shutting down GTFS scheduler...")
        scheduler.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start the scheduler
    scheduler.start()
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        scheduler.stop()
        sys.exit(0)


if __name__ == "__main__":
    run_scheduler()