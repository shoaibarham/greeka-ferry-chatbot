"""Extension initialization module to avoid circular imports."""
from flask_sqlalchemy import SQLAlchemy

# Initialize SQLAlchemy without binding to app
db = SQLAlchemy()