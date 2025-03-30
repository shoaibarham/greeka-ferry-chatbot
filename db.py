import sqlite3
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Path to SQLite database
DB_PATH = 'gtfs.db'

@contextmanager
def get_db_connection():
    """Get a connection to the SQLite database."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # Enable row factory
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {str(e)}")
        raise
    finally:
        if conn:
            conn.close()

def execute_query(query_string, params=None):
    """Execute a raw SQL query and return results."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if params:
                cursor.execute(query_string, params)
            else:
                cursor.execute(query_string)
                
            results = cursor.fetchall()
            return results
    except sqlite3.Error as e:
        logger.error(f"Error executing query: {str(e)}")
        raise

def get_connection():
    """Get a database connection."""
    return sqlite3.connect(DB_PATH)
