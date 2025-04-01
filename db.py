"""
Database connection utility functions for the ferry application.
"""
import os
import logging
import sqlite3
from typing import List, Tuple, Any, Optional, Union

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session

from config import DATABASE_URL

logger = logging.getLogger(__name__)

# Create SQLAlchemy engine and session
engine = create_engine(DATABASE_URL)
session_factory = sessionmaker(bind=engine)
db_session = scoped_session(session_factory)

def get_db_connection():
    """
    Get a connection to the database.
    This is used for raw SQL queries outside the ORM.
    
    Returns:
        sqlite3.Connection: Database connection object
    """
    if 'sqlite' in DATABASE_URL:
        # For SQLite
        db_path = DATABASE_URL.replace('sqlite:///', '')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    else:
        # For PostgreSQL, we should use SQLAlchemy's connection
        return engine.connect()

def execute_query(query_string, params=None):
    """
    Execute a raw SQL query and return results.
    
    Args:
        query_string (str): SQL query to execute
        params (list, optional): Parameters for the query
        
    Returns:
        list: List of rows returned by the query
    """
    try:
        logger.debug(f"Executing query: {query_string}")
        if params:
            logger.debug(f"With parameters: {params}")
        
        if 'sqlite' in DATABASE_URL:
            # For SQLite, use sqlite3 directly
            conn = get_db_connection()
            if params:
                cursor = conn.execute(query_string, params)
            else:
                cursor = conn.execute(query_string)
            
            results = cursor.fetchall()
            conn.close()
            
            # Convert sqlite3.Row objects to tuples for consistent handling
            return [tuple(row) for row in results]
        else:
            # For PostgreSQL, use SQLAlchemy
            with engine.connect() as connection:
                if params:
                    result = connection.execute(text(query_string), params)
                else:
                    result = connection.execute(text(query_string))
                
                return [row for row in result]
    
    except Exception as e:
        logger.error(f"Database query error: {e}")
        logger.error(f"Query: {query_string}")
        if params:
            logger.error(f"Parameters: {params}")
        raise

def get_connection():
    """
    Get a database connection.
    This is a convenience wrapper around get_db_connection.
    
    Returns:
        Connection: Database connection object
    """
    return get_db_connection()