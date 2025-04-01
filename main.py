"""
Main entry point for the ferry information application.
This connects all the components together.
"""
import os
import logging
from flask import render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
import json
from datetime import datetime

from app import app, login_manager
from ext import db
from new_models import User, Route, DateAndVessel, VesselIndicativePrice, VesselAccommodationPrice
from new_ferry_agent import FerryAgent
from new_data_loader import update_ferry_data
from forms import LoginForm

# Set up logging
logger = logging.getLogger(__name__)

# Global variables
ferry_agent = None

@login_manager.user_loader
def load_user(user_id):
    """Load user from the database using SQLAlchemy."""
    return User.query.get(int(user_id))

def initialize_databases():
    """Initialize both the main and historical databases if needed."""
    with app.app_context():
        db.create_all()
        create_admin_user()

def initialize_agent():
    """Initialize the ferry agent if not already initialized."""
    global ferry_agent
    if ferry_agent is None:
        try:
            ferry_agent = FerryAgent()
            logger.info("Ferry agent initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ferry agent: {str(e)}")
            ferry_agent = None

def create_admin_user():
    """Create an admin user if none exists."""
    try:
        admin = User.query.filter_by(is_admin=True).first()
        if not admin:
            admin = User(
                username="admin",
                email="admin@ferrysearch.com",
                is_admin=True
            )
            admin.set_password("admin123")  # Default password, should be changed
            db.session.add(admin)
            db.session.commit()
            logger.info("Admin user created")
    except Exception as e:
        logger.error(f"Error creating admin user: {str(e)}")

@app.route('/')
def index():
    """Render the main page of the ferry chatbot application."""
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle admin login."""
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            return redirect(url_for('admin'))
        flash('Invalid username or password')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    """Handle admin logout."""
    logout_user()
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin():
    """Render the admin panel for managing ferry data."""
    if not current_user.is_admin:
        flash('You do not have admin privileges')
        return redirect(url_for('index'))
    return render_template('admin.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Process user queries and return AI-generated responses
    using the Gemini model and FerryAgent.
    """
    global ferry_agent
    if ferry_agent is None:
        initialize_agent()
        if ferry_agent is None:
            return jsonify({"error": "Ferry agent is not available"})
    
    data = request.json
    query = data.get('query', '')
    session_id = data.get('session_id', datetime.now().strftime('%Y%m%d%H%M%S'))
    
    try:
        response = ferry_agent.query(query, session_id)
        return jsonify({
            "response": response,
            "session_id": session_id
        })
    except Exception as e:
        logger.error(f"Error processing chat query: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)})

@app.route('/api/update-data', methods=['POST'])
@login_required
def update_data():
    """
    Endpoint to trigger main data update process.
    This would typically be called by a scheduled task.
    """
    if not current_user.is_admin:
        return jsonify({"error": "Admin privileges required"})
    
    try:
        message = update_ferry_data()
        return jsonify({"message": message})
    except Exception as e:
        logger.error(f"Error updating data: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)})

@app.route('/api/update-historical-data', methods=['POST'])
@login_required
def update_historical_data():
    """
    Endpoint to trigger historical data update process.
    Updates the historical route database with past and future route availability.
    """
    if not current_user.is_admin:
        return jsonify({"error": "Admin privileges required"})
    
    try:
        # Would implement historical data update logic here
        return jsonify({"message": "Historical data update not yet implemented"})
    except Exception as e:
        logger.error(f"Error updating historical data: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)})

@app.route('/api/get-ports', methods=['GET'])
def get_ports():
    """Get a list of all available ports."""
    try:
        # Using the new schema to get unique ports
        origin_ports = db.session.query(
            Route.origin_port_code, 
            Route.origin_port_name
        ).distinct().all()
        
        dest_ports = db.session.query(
            Route.destination_port_code,
            Route.destination_port_name
        ).distinct().all()
        
        # Combine and remove duplicates
        all_ports = set(origin_ports + dest_ports)
        
        return jsonify([{"code": code, "name": name} for code, name in all_ports])
    except Exception as e:
        logger.error(f"Error getting ports: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)})

@app.route('/api/database-status', methods=['GET'])
@login_required
def database_status():
    """Get the status of the database."""
    if not current_user.is_admin:
        return jsonify({"error": "Admin privileges required"})
    
    try:
        route_count = Route.query.count()
        schedule_count = DateAndVessel.query.count()
        vessel_price_count = VesselIndicativePrice.query.count()
        accommodation_price_count = VesselAccommodationPrice.query.count()
        
        return jsonify({
            "routes": route_count,
            "schedules": schedule_count,
            "vessel_prices": vessel_price_count,
            "accommodation_prices": accommodation_price_count
        })
    except Exception as e:
        logger.error(f"Error getting database status: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)})

def run_scheduled_update():
    """Run scheduled updates for ferry data."""
    with app.app_context():
        try:
            logger.info("Running scheduled data update")
            message = update_ferry_data()
            logger.info(message)
        except Exception as e:
            logger.error(f"Scheduled update failed: {str(e)}", exc_info=True)

# Initialize the database and agent when the application starts
if __name__ == '__main__':
    initialize_databases()
    initialize_agent()
    app.run(host='0.0.0.0', port=5000, debug=True)