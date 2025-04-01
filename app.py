"""
Main application module for the ferry information system.
"""
import os
import logging
from flask import Flask
from flask_login import LoginManager

from ext import db
from config import SECRET_KEY, DATABASE_URL

# Set up logging
logging.basicConfig(level=logging.INFO, 
                  format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create Flask application
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 300,
    'pool_pre_ping': True,
}

# Initialize extensions
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Import routes and models after app is created
with app.app_context():
    from new_models import User, Route, DateAndVessel, VesselIndicativePrice, VesselAccommodationPrice
    db.create_all()  # Make sure tables exist