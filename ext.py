"""Extension initialization module to avoid circular imports."""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Initialize extensions without app
db = SQLAlchemy()
login_manager = LoginManager()