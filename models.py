from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from ext import db

# Models based on the SQLite schema

class Route(db.Model):
    """Model representing ferry routes."""
    __tablename__ = 'routes'
    
    route_id = db.Column(db.Integer, primary_key=True)
    route_number = db.Column(db.String(50), nullable=True)
    company = db.Column(db.String(255), nullable=True)
    company_code = db.Column(db.String(20), nullable=True)
    origin_port_code = db.Column(db.String(20), nullable=True)
    origin_port_name = db.Column(db.String(255), nullable=True)
    destination_port_code = db.Column(db.String(20), nullable=True)
    destination_port_name = db.Column(db.String(255), nullable=True)
    departure_time = db.Column(db.String(10), nullable=True)  # HH:MM format
    arrival_time = db.Column(db.String(10), nullable=True)  # HH:MM format
    origin_port_stop = db.Column(db.Integer, nullable=True)
    destination_port_stop = db.Column(db.Integer, nullable=True)
    departure_offset = db.Column(db.Integer, nullable=True)
    arrival_offset = db.Column(db.Integer, nullable=True)
    duration = db.Column(db.Integer, nullable=True)  # Duration in minutes
    
    # Relationships
    dates_and_vessels = db.relationship('DateAndVessel', backref='route', lazy=True)
    vessels_and_prices = db.relationship('VesselAndIndicativePrice', backref='route', lazy=True)
    accommodations = db.relationship('VesselAndAccommodationPrice', backref='route', lazy=True)
    
    def __repr__(self):
        return f"<Route {self.route_id}: {self.origin_port_code} to {self.destination_port_code}>"

class DateAndVessel(db.Model):
    """Model representing dates and vessels for routes."""
    __tablename__ = 'dates_and_vessels'
    
    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.Integer, db.ForeignKey('routes.route_id'), nullable=False)
    schedule_date = db.Column(db.String(20), nullable=True)  # YYYY-MM-DD format
    vessel = db.Column(db.String(255), nullable=True)  # Format: "CODE___NAME"
    
    def __repr__(self):
        return f"<DateAndVessel: Route {self.route_id} on {self.schedule_date} with {self.vessel}>"

class VesselAndIndicativePrice(db.Model):
    """Model representing vessel indicative prices for routes."""
    __tablename__ = 'vessels_and_indicative_prices'
    
    route_id = db.Column(db.Integer, db.ForeignKey('routes.route_id'), primary_key=True)
    vessel = db.Column(db.String(255), primary_key=True)  # Format: "CODE___NAME"
    indicative_price = db.Column(db.Integer, nullable=True)  # Price in cents
    
    def __repr__(self):
        return f"<VesselPrice: Route {self.route_id}, {self.vessel}, €{self.indicative_price/100:.2f}>"

class VesselAndAccommodationPrice(db.Model):
    """Model representing vessel accommodation prices for routes."""
    __tablename__ = 'vessels_and_accommodation_prices'
    
    route_id = db.Column(db.Integer, db.ForeignKey('routes.route_id'), primary_key=True)
    vessel = db.Column(db.String(255), primary_key=True)  # Format: "CODE___NAME"
    accommodation_type = db.Column(db.String(255), primary_key=True)  # Format: "CODE___NAME"
    price = db.Column(db.Integer, nullable=True)  # Price in cents
    
    def __repr__(self):
        return f"<AccommodationPrice: Route {self.route_id}, {self.vessel}, {self.accommodation_type}, €{self.price/100:.2f}>"

# Keep this User model for authentication
class User(UserMixin, db.Model):
    """Model representing admin users for the system."""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    
    def set_password(self, password):
        """Set password hash."""
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        """Check if password is correct."""
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f"<User {self.username}>"
