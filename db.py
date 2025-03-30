from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL

# Create engine and session
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def execute_query(query_string, params=None):
    """Execute a raw SQL query and return results."""
    with Session() as session:
        result = session.execute(text(query_string), params)
        return result.fetchall()

def get_connection():
    """Get a database connection from the engine."""
    return engine.connect()
