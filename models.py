from datetime import datetime
from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import relationship
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from ext import db

class FerryCompany(db.Model):
    """Model representing ferry companies that operate routes."""
    __tablename__ = 'ferry_companies'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(10), nullable=False, unique=True)
    routes = relationship("FerryRoute", back_populates="company")
    
    def __repr__(self):
        return f"<FerryCompany {self.name} ({self.code})>"

class Port(db.Model):
    """Model representing ports that ferries depart from and arrive at."""
    __tablename__ = 'ports'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), nullable=False, unique=True)
    name = db.Column(db.String(255), nullable=False)
    
    def __repr__(self):
        return f"<Port {self.name} ({self.code})>"

class Vessel(db.Model):
    """Model representing ferry vessels."""
    __tablename__ = 'vessels'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    vessel_key = db.Column(db.String(255), nullable=False, unique=True)  # Combined code and name
    
    def __repr__(self):
        return f"<Vessel {self.name} ({self.code})>"

class Accommodation(db.Model):
    """Model representing accommodation types available on vessels."""
    __tablename__ = 'accommodations'
    
    id = db.Column(db.Integer, primary_key=True)
    vessel_id = db.Column(db.Integer, ForeignKey('vessels.id'), nullable=False)
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    ferry_route_id = db.Column(db.Integer, ForeignKey('ferry_routes.id'), nullable=False)  # Changed to reference the primary key
    route_id = db.Column(db.String(50), nullable=False)  # Keep as a non-FK field for reference
    price = db.Column(db.Integer, nullable=False)  # Price in cents
    
    vessel = relationship("Vessel")
    route = relationship("FerryRoute", foreign_keys=[ferry_route_id])
    
    def __repr__(self):
        return f"<Accommodation {self.name} on {self.vessel.name} - €{self.price/100:.2f}>"

class FerryRoute(db.Model):
    """Model representing ferry routes between ports."""
    __tablename__ = 'ferry_routes'
    
    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.String(50), nullable=False, index=True)  # Changed from unique=True to index=True
    company_id = db.Column(db.Integer, ForeignKey('ferry_companies.id'), nullable=False)
    origin_port_id = db.Column(db.Integer, ForeignKey('ports.id'), nullable=False)
    destination_port_id = db.Column(db.Integer, ForeignKey('ports.id'), nullable=False)
    origin_port_stop = db.Column(db.Integer, nullable=False)
    destination_port_stop = db.Column(db.Integer, nullable=False)
    departure_time = db.Column(db.String(5), nullable=False)  # HH:MM format
    arrival_time = db.Column(db.String(5), nullable=False)  # HH:MM format
    departure_offset = db.Column(db.Integer, nullable=False)
    arrival_offset = db.Column(db.Integer, nullable=False)
    duration = db.Column(db.Integer, nullable=False)  # Duration in minutes
    
    company = relationship("FerryCompany", back_populates="routes")
    origin_port = relationship("Port", foreign_keys=[origin_port_id])
    destination_port = relationship("Port", foreign_keys=[destination_port_id])
    schedules = relationship("Schedule", back_populates="route")
    
    def __repr__(self):
        return f"<FerryRoute {self.origin_port.code} to {self.destination_port.code}>"

class Schedule(db.Model):
    """Model representing specific schedule dates for ferry routes."""
    __tablename__ = 'schedules'
    
    id = db.Column(db.Integer, primary_key=True)
    ferry_route_id = db.Column(db.Integer, ForeignKey('ferry_routes.id'), nullable=False)  # Changed to reference the primary key
    route_id = db.Column(db.String(50), nullable=False)  # Keep as a non-FK field for reference
    date = db.Column(db.Date, nullable=False)
    vessel_id = db.Column(db.Integer, ForeignKey('vessels.id'), nullable=False)
    indicative_price = db.Column(db.Integer, nullable=False)  # Price in cents
    
    route = relationship("FerryRoute", foreign_keys=[ferry_route_id], back_populates="schedules")
    vessel = relationship("Vessel")
    
    __table_args__ = (db.UniqueConstraint('ferry_route_id', 'date', name='_route_date_uc'),)
    
    def __repr__(self):
        return f"<Schedule {self.route.origin_port.code}-{self.route.destination_port.code} on {self.date}>"


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
