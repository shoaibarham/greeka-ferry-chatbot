"""
Email fetcher for GTFS data updates.
This module connects to an email account and fetches attachments containing GTFS data.
"""

import os
import re
import email
import imaplib
import logging
from datetime import datetime
from email.header import decode_header
import tempfile
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='email_updates.log'
)

logger = logging.getLogger(__name__)

class EmailFetcher:
    """
    Class to fetch GTFS data from email attachments.
    """
    def __init__(self, email_address=None, password=None, imap_server="imap.gmail.com", 
                 imap_port=993, folder="INBOX"):
        """
        Initialize the EmailFetcher with email credentials.
        
        Args:
            email_address: Email address to connect to
            password: Password or app password for the email account
            imap_server: IMAP server address (default: imap.gmail.com)
            imap_port: IMAP server port (default: 993)
            folder: Email folder to check (default: INBOX)
        """
        self.email_address = email_address or os.environ.get("GTFS_EMAIL")
        self.password = password or os.environ.get("GTFS_PASSWORD")
        self.imap_server = imap_server
        self.imap_port = imap_port
        self.folder = folder
        self.connection = None
        
        if not self.email_address or not self.password:
            logger.warning("Email credentials not provided. Use set_credentials() before connecting.")
    
    def set_credentials(self, email_address, password):
        """
        Set or update email credentials.
        
        Args:
            email_address: Email address to connect to
            password: Password or app password for the email account
        """
        self.email_address = email_address
        self.password = password
        logger.info("Email credentials updated.")
    
    def connect(self):
        """
        Connect to the email server.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        if not self.email_address or not self.password:
            logger.error("Email credentials not provided.")
            return False
            
        try:
            # Clean up any existing connection
            if self.connection:
                try:
                    self.disconnect()
                except:
                    pass
                self.connection = None
                
            # Create a new connection
            logger.info(f"Connecting to {self.imap_server}:{self.imap_port} as {self.email_address}")
            self.connection = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            
            # Attempt login
            logger.info("Attempting login...")
            self.connection.login(self.email_address, self.password)
            
            # Select mailbox
            logger.info(f"Selecting folder: {self.folder}")
            status, data = self.connection.select(self.folder)
            
            if status != 'OK':
                logger.error(f"Failed to select folder {self.folder}: {data}")
                return False
                
            logger.info(f"Successfully connected to {self.imap_server} as {self.email_address}")
            return True
            
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP error connecting to email server: {str(e)}")
            self.connection = None
            return False
        except ConnectionRefusedError as e:
            logger.error(f"Connection refused to {self.imap_server}: {str(e)}")
            self.connection = None
            return False
        except Exception as e:
            logger.error(f"Failed to connect to email server: {str(e)}")
            self.connection = None
            return False
    
    def disconnect(self):
        """
        Disconnect from the email server.
        """
        if self.connection:
            try:
                self.connection.close()
                self.connection.logout()
                logger.info("Disconnected from email server")
            except Exception as e:
                logger.error(f"Error disconnecting from email server: {str(e)}")
    
    def search_emails(self, subject_filter=None, sender_filter=None, 
                      since_date=None, unread_only=False, limit=10):
        """
        Search for emails matching the specified criteria.
        
        Args:
            subject_filter: Filter by subject containing this text
            sender_filter: Filter by sender email address
            since_date: Only fetch emails after this date (datetime object)
            unread_only: Only fetch unread emails if True
            limit: Maximum number of emails to fetch (default: 10)
            
        Returns:
            list: List of email IDs matching the criteria
        """
        # Ensure we have a connection
        if not self.connection:
            logger.info("No active connection, attempting to connect")
            if not self.connect():
                logger.error("Failed to establish connection")
                return []
        
        # Build search criteria
        search_criteria = []
        
        if unread_only:
            search_criteria.append('UNSEEN')
            
        if subject_filter:
            search_criteria.append(f'SUBJECT "{subject_filter}"')
            
        if sender_filter:
            search_criteria.append(f'FROM "{sender_filter}"')
            
        if since_date:
            date_str = since_date.strftime("%d-%b-%Y")
            search_criteria.append(f'SINCE "{date_str}"')
        
        search_string = ' '.join(search_criteria) if search_criteria else 'ALL'
        
        try:
            logger.info(f"Searching emails with criteria: {search_string}")
            
            # Execute search query
            if self.connection is None:
                logger.error("Connection is None, cannot search")
                return []
                
            result, data = self.connection.search(None, search_string)
            
            if result != 'OK':
                logger.error(f"Search failed with status: {result}")
                return []
            
            if not data or not data[0]:
                logger.info("No data returned from search")
                return []
                
            # Process email IDs from search result
            email_ids = data[0].split()
            
            # Limit the number of results
            if limit and len(email_ids) > limit:
                email_ids = email_ids[-limit:]
                
            logger.info(f"Found {len(email_ids)} emails matching criteria")
            return email_ids
            
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP error during search: {str(e)}")
            # Try to reconnect and search again
            if self.connect():
                try:
                    result, data = self.connection.search(None, search_string)
                    if result == 'OK' and data and data[0]:
                        email_ids = data[0].split()
                        if limit and len(email_ids) > limit:
                            email_ids = email_ids[-limit:]
                        return email_ids
                except Exception:
                    pass
            return []
        except Exception as e:
            logger.error(f"Error searching emails: {str(e)}")
            return []
    
    def fetch_attachments(self, email_id, save_dir=None, json_only=True):
        """
        Fetch and save attachments from a specific email.
        
        Args:
            email_id: Email ID to fetch attachments from
            save_dir: Directory to save attachments (default: temp directory)
            json_only: Only download JSON attachments if True
            
        Returns:
            list: List of paths to saved attachments
        """
        # Ensure we have a connection
        if not self.connection:
            logger.info("No active connection, attempting to connect")
            if not self.connect():
                logger.error("Failed to establish connection")
                return []
                
        # Set up save directory
        if not save_dir:
            save_dir = tempfile.gettempdir()
        
        # Ensure save directory exists
        os.makedirs(save_dir, exist_ok=True)
            
        try:
            logger.info(f"Fetching email with ID: {email_id}")
            
            # Check if connection is valid
            if self.connection is None:
                logger.error("Connection is None, cannot fetch email")
                return []
                
            # Fetch the email
            result, data = self.connection.fetch(email_id, '(RFC822)')
            
            if result != 'OK':
                logger.error(f"Failed to fetch email {email_id}: {result}")
                return []
                
            if not data or not data[0] or len(data[0]) < 2:
                logger.error("Invalid data format returned from fetch")
                return []
                
            raw_email = data[0][1]
            if not isinstance(raw_email, bytes):
                logger.error(f"Raw email data is not bytes, but {type(raw_email)}")
                raw_email = bytes(str(raw_email), 'utf-8')
                
            # Parse the email
            email_message = email.message_from_bytes(raw_email)
            
            # Get email subject for logging
            subject = decode_email_header(email_message.get('Subject', 'No Subject'))
            sender = decode_email_header(email_message.get('From', 'Unknown Sender'))
            logger.info(f"Processing email from {sender}: {subject}")
            
            saved_files = []
            
            # Process each part of the email
            for part in email_message.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                    
                filename = part.get_filename()
                if not filename:
                    continue
                
                try:
                    # Decode filename if needed
                    decoded_header = decode_header(filename)[0]
                    if decoded_header[1]:  # Has encoding info
                        filename = decoded_header[0].decode(decoded_header[1])
                    elif isinstance(decoded_header[0], bytes):
                        filename = decoded_header[0].decode('utf-8', errors='replace')
                    else:
                        filename = decoded_header[0]
                except Exception as e:
                    logger.warning(f"Error decoding filename: {str(e)}")
                    # Use a safe default if decoding fails
                    filename = f"attachment_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
                
                # Check if it's a JSON file if json_only is True
                if json_only and not filename.lower().endswith('.json'):
                    logger.info(f"Skipping non-JSON attachment: {filename}")
                    continue
                    
                # Clean up filename to avoid issues
                filename = re.sub(r'[^\w\.-]', '_', filename)
                
                # Create full path for saving
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                save_path = os.path.join(save_dir, f"{timestamp}_{filename}")
                
                try:
                    # Save the attachment
                    payload = part.get_payload(decode=True)
                    if payload:
                        with open(save_path, 'wb') as f:
                            f.write(payload)
                        
                        logger.info(f"Saved attachment: {save_path}")
                        saved_files.append(save_path)
                    else:
                        logger.warning(f"Empty payload for attachment: {filename}")
                except Exception as e:
                    logger.error(f"Error saving attachment {filename}: {str(e)}")
                
            return saved_files
            
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP error fetching email {email_id}: {str(e)}")
            # Try to reconnect and fetch again
            if self.connect():
                try:
                    result, data = self.connection.fetch(email_id, '(RFC822)')
                    if result == 'OK' and data and data[0]:
                        # Process the email (simplified for retry)
                        raw_email = data[0][1]
                        if isinstance(raw_email, bytes):
                            email_message = email.message_from_bytes(raw_email)
                            saved_files = []
                            for part in email_message.walk():
                                if part.get_content_maintype() != 'multipart' and part.get_filename():
                                    # Basic saving logic for retry
                                    filename = re.sub(r'[^\w\.-]', '_', part.get_filename())
                                    if json_only and not filename.lower().endswith('.json'):
                                        continue
                                    save_path = os.path.join(save_dir, f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}")
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        with open(save_path, 'wb') as f:
                                            f.write(payload)
                                        saved_files.append(save_path)
                            return saved_files
                except Exception:
                    pass
            return []
        except Exception as e:
            logger.error(f"Error fetching attachments from email {email_id}: {str(e)}")
            return []
    
    def fetch_recent_gtfs_data(self, subject_filter="GTFS", days=7, save_dir="./gtfs_updates"):
        """
        Fetch all recent GTFS data from emails.
        
        Args:
            subject_filter: Subject text to filter emails by (default: "GTFS")
            days: Number of days to look back for emails
            save_dir: Directory to save attachments
            
        Returns:
            list: Paths to downloaded GTFS files
        """
        since_date = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        since_date = since_date.replace(day=since_date.day - days)
        
        # Create save directory if it doesn't exist
        os.makedirs(save_dir, exist_ok=True)
        
        # Search for matching emails
        email_ids = self.search_emails(
            subject_filter=subject_filter,
            since_date=since_date
        )
        
        if not email_ids:
            logger.info(f"No emails found matching subject '{subject_filter}' in the last {days} days")
            return []
        
        # Process each email and collect all attachment paths
        all_attachments = []
        for email_id in email_ids:
            attachments = self.fetch_attachments(email_id, save_dir=save_dir)
            all_attachments.extend(attachments)
        
        return all_attachments
    
    def validate_gtfs_json(self, file_path):
        """
        Validate that a downloaded file is valid GTFS JSON data.
        
        Args:
            file_path: Path to the JSON file
            
        Returns:
            bool: True if valid, False otherwise
        """
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # Basic validation - check if the file contains routes data
            if 'routes' not in data:
                logger.warning(f"File {file_path} does not contain routes data")
                return False
                
            # Count the number of routes for logging
            route_count = len(data['routes'])
            logger.info(f"File {file_path} contains {route_count} routes")
            
            return True
        except json.JSONDecodeError:
            logger.error(f"File {file_path} is not valid JSON")
            return False
        except Exception as e:
            logger.error(f"Error validating GTFS data: {str(e)}")
            return False


def decode_email_header(header):
    """Helper function to decode email headers"""
    if header is None:
        return ""
    decoded_header = decode_header(header)[0]
    if decoded_header[1]:
        return decoded_header[0].decode(decoded_header[1])
    else:
        if isinstance(decoded_header[0], bytes):
            return decoded_header[0].decode('utf-8', errors='replace')
        return decoded_header[0]


if __name__ == "__main__":
    # Simple test
    fetcher = EmailFetcher()
    # To run this test, you need to set environment variables or provide credentials:
    # fetcher.set_credentials("your_email@example.com", "your_password")
    # fetcher.connect()
    # files = fetcher.fetch_recent_gtfs_data()
    # print(f"Downloaded {len(files)} GTFS files")