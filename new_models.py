"""
SQLAlchemy models for the ferry application.
"""
from sqlalchemy import Column, Integer, String, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from ext import db

class Route(db.Model):
    """Model representing ferry routes between ports."""
    __tablename__ = 'routes'
    
    route_id = Column(Integer, primary_key=True)
    route_number = Column(String, nullable=False)
    company = Column(String, nullable=False)
    company_code = Column(String, nullable=False)
    origin_port_code = Column(String, nullable=False)
    origin_port_name = Column(String, nullable=False)
    destination_port_code = Column(String, nullable=False)
    destination_port_name = Column(String, nullable=False)
    departure_time = Column(String, nullable=False)
    arrival_time = Column(String, nullable=False)
    origin_port_stop = Column(Integer, nullable=False)
    destination_port_stop = Column(Integer, nullable=False)
    departure_offset = Column(Integer, nullable=False)
    arrival_offset = Column(Integer, nullable=False)
    duration = Column(Integer, nullable=False)
    
    dates = relationship("DateAndVessel", back_populates="route")
    indicative_prices = relationship("VesselIndicativePrice", back_populates="route")
    accommodation_prices = relationship("VesselAccommodationPrice", back_populates="route")
    
    def __repr__(self):
        return f"<Route {self.route_id}: {self.origin_port_name} to {self.destination_port_name}>"

class DateAndVessel(db.Model):
    """Model representing dates that a vessel operates on a route."""
    __tablename__ = 'dates_and_vessels'
    
    id = Column(Integer, primary_key=True)
    route_id = Column(Integer, ForeignKey('routes.route_id'), nullable=False)
    schedule_date = Column(Date, nullable=False)
    vessel = Column(String, nullable=False)
    
    route = relationship("Route", back_populates="dates")
    
    __table_args__ = (
        UniqueConstraint('route_id', 'schedule_date', 'vessel', name='_route_date_vessel_uc'),
    )
    
    def __repr__(self):
        return f"<DateAndVessel {self.id}: Route {self.route_id} on {self.schedule_date}>"

class VesselIndicativePrice(db.Model):
    """Model representing indicative prices for vessels on routes."""
    __tablename__ = 'vessels_and_indicative_prices'
    
    route_id = Column(Integer, ForeignKey('routes.route_id'), primary_key=True)
    vessel = Column(String, primary_key=True)
    indicative_price = Column(Integer, nullable=False)  # Price in cents
    
    route = relationship("Route", back_populates="indicative_prices")
    
    def __repr__(self):
        return f"<VesselIndicativePrice: Route {self.route_id}, Vessel {self.vessel}, Price {self.indicative_price}>"

class VesselAccommodationPrice(db.Model):
    """Model representing accommodation prices for vessels on routes."""
    __tablename__ = 'vessels_and_accommodation_prices'
    
    route_id = Column(Integer, ForeignKey('routes.route_id'), primary_key=True)
    vessel = Column(String, primary_key=True)
    accommodation_type = Column(String, primary_key=True)
    price = Column(Integer, nullable=False)  # Price in cents
    
    route = relationship("Route", back_populates="accommodation_prices")
    
    def __repr__(self):
        return f"<VesselAccommodationPrice: Route {self.route_id}, Vessel {self.vessel}, Type {self.accommodation_type}, Price {self.price}>"

class User(UserMixin, db.Model):
    """Model representing users of the system."""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    is_admin = Column(Integer, default=0)
    
    def set_password(self, password):
        """Set password hash."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if password is correct."""
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f"<User {self.username}>"