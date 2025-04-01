import os
import logging
import sqlite3
from datetime import datetime
import subprocess
import threading
import time

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from forms import LoginForm

# Initialize logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")

# Configure SQLAlchemy
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///user_auth.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize extensions
from ext import db, login_manager
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'

# Import models (after initializing db to avoid circular imports)
from models import User

# Database paths
DB_PATH = 'gtfs.db'
HISTORICAL_DB_PATH = 'previous_db.db'

# Initialize ferry agent (outside the routes to avoid recreation on each request)
ferry_agent = None

@login_manager.user_loader
def load_user(user_id):
    """Load user from the database using SQLAlchemy."""
    try:
        from models import User
        return User.query.get(int(user_id))
    except Exception as e:
        logger.error(f"Error loading user: {str(e)}")
        return None

def initialize_databases():
    """Initialize both the main and historical databases if needed."""
    # Initialize main database
    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0:
        logger.info("Initializing main ferry database...")
        try:
            # Use sqlite_loader directly
            from sqlite_loader import load_data
            from config import DEFAULT_DATA_PATH
            load_data(json_path=DEFAULT_DATA_PATH, db_path=DB_PATH)
            logger.info("Main database initialization complete")
        except Exception as e:
            logger.error(f"Failed to initialize main database: {str(e)}")
            raise
    
    # Check if the tables exist in the main database
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='routes'")
        if not cursor.fetchone():
            logger.info("Routes table not found. Initializing database tables...")
            from sqlite_loader import create_tables
            create_tables(cursor)
            conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error checking database tables: {str(e)}")
    
    # Initialize historical database
    if not os.path.exists(HISTORICAL_DB_PATH) or os.path.getsize(HISTORICAL_DB_PATH) == 0:
        logger.info("Initializing historical ferry database...")
        try:
            import initialize_historical_data
            initialize_historical_data.main()
            logger.info("Historical database initialization complete")
        except Exception as e:
            logger.error(f"Failed to initialize historical database: {str(e)}")
            raise

def initialize_agent():
    """Initialize the ferry agent if not already initialized."""
    global ferry_agent
    if ferry_agent is None:
        from ferry_agent import FerryAgent
        try:
            # Make sure databases are initialized first
            initialize_databases()
            
            ferry_agent = FerryAgent()
            logger.info("Ferry agent initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ferry agent: {str(e)}")
            raise

# Initialize the ferry agent at app startup
initialize_agent()

# Create admin user if none exists (will be called in main.py)
def create_admin_user():
    try:
        """Create an admin user if none exists."""
        # Create tables if they don't exist
        db.create_all()
        
        # Check if there are any users
        if User.query.count() == 0:
            # Create admin user
            admin = User(username="admin", email="admin@example.com", is_admin=True)
            admin.set_password("admin123")  # Default password, should be changed
            db.session.add(admin)
            db.session.commit()
            logger.info("Created default admin user")
    except Exception as e:
        logger.error(f"Error creating admin user: {str(e)}")

# Routes
@app.route("/")
def index():
    """Render the main page of the ferry chatbot application."""
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Handle admin login."""
    # If user is already logged in, redirect to admin panel
    if current_user.is_authenticated:
        return redirect(url_for('admin'))
    
    form = LoginForm()
    
    if form.validate_on_submit():
        # Find user by username
        user = User.query.filter_by(username=form.username.data).first()
        
        # Check if user exists and password is correct
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('login'))
        
        # Log in user
        login_user(user, remember=form.remember_me.data)
        
        # Redirect to admin panel
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('admin')
            
        return redirect(next_page)
    
    return render_template("login.html", form=form)

@app.route("/logout")
@login_required
def logout():
    """Handle admin logout."""
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route("/admin")
@login_required
def admin():
    """Render the admin panel for managing ferry data."""
    # Only allow access to admin users
    if not current_user.is_admin:
        flash('You do not have permission to access the admin panel', 'danger')
        return redirect(url_for('index'))
    
    return render_template("admin.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Process user queries and return AI-generated responses
    using the Gemini model and FerryAgent.
    """
    try:
        # Make sure agent is initialized
        if ferry_agent is None:
            initialize_agent()
            
        # Get user message
        data = request.json
        user_message = data.get("message", "")
        conversation_id = data.get("conversation_id", None)
        
        # Initialize or retrieve conversation history
        if not conversation_id:
            conversation_id = datetime.now().strftime("%Y%m%d%H%M%S")
            session[conversation_id] = []
        
        # Process the query with ferry agent
        response = ferry_agent.query(user_message, conversation_id)
        
        # Return response to frontend
        return jsonify({
            "response": response,
            "conversation_id": conversation_id
        })
    
    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}", exc_info=True)
        return jsonify({
            "error": "An error occurred while processing your request.",
            "details": str(e)
        }), 500

@app.route("/api/update_data", methods=["POST"])
def update_data():
    """
    Endpoint to trigger main data update process.
    This would typically be called by a scheduled task.
    """
    try:
        import sqlite_loader
        source_file = request.json.get("source_file", "attached_assets/GTFS_data_v5.json")
        result = sqlite_loader.load_data(json_path=source_file, db_path=DB_PATH)
        
        # Log the update
        update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("data_updates.log", "a") as f:
            f.write(f"{update_time} - INFO - Successfully updated ferry data from {source_file}\n")
        
        # Reinitialize the ferry agent to use the updated data
        global ferry_agent
        from ferry_agent import FerryAgent
        ferry_agent = FerryAgent()
        
        return jsonify({"success": True, "message": "Successfully updated ferry data"})
    except Exception as e:
        logger.error(f"Error updating ferry data: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to update ferry data",
            "details": str(e)
        }), 500
        
@app.route("/api/update_historical_data", methods=["POST"])
def update_historical_data():
    """
    Endpoint to trigger historical data update process.
    Updates the historical route database with past and future route availability.
    """
    try:
        import historical_data_loader
        source_file = request.json.get("source_file", "attached_assets/GTFS appear dates.json")
        result = historical_data_loader.load_historical_data(source_file)
        
        # Reinitialize the ferry agent to incorporate the updated historical data
        global ferry_agent
        from ferry_agent import FerryAgent
        ferry_agent = FerryAgent()
        
        return jsonify({"success": True, "message": result})
    except Exception as e:
        logger.error(f"Error updating historical ferry data: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to update historical ferry data",
            "details": str(e)
        }), 500

@app.route("/api/ports", methods=["GET"])
def get_ports():
    """Get a list of all available ports."""
    try:
        search_term = request.args.get("search", "")
        
        if ferry_agent:
            port_info = ferry_agent.get_port_information(search_term)
            # Split the port info string into a list of ports
            ports = [{"code": line.split(":")[0].strip(), "name": line.split(":")[1].strip()} 
                     for line in port_info.split("\n") if ":" in line]
            return jsonify({"ports": ports})
        else:
            return jsonify({"error": "Ferry agent not initialized"}), 500
    except Exception as e:
        logger.error(f"Error retrieving ports: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/database-status", methods=["GET"])
def database_status():
    """Get the status of the database."""
    try:
        # Count entries in main database
        table_counts = {}
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get counts from each table
        cursor.execute("SELECT COUNT(*) FROM routes")
        table_counts["routes"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM dates_and_vessels")
        table_counts["dates_and_vessels"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM vessels_and_indicative_prices")
        table_counts["vessels_and_prices"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM vessels_and_accommodation_prices")
        table_counts["accommodation_prices"] = cursor.fetchone()[0]
        
        conn.close()
        
        # Count entries in historical database
        historical_counts = {}
        if os.path.exists(HISTORICAL_DB_PATH):
            conn = sqlite3.connect(HISTORICAL_DB_PATH)
            cursor = conn.cursor()
            
            # Get the count of historical date ranges
            try:
                cursor.execute("SELECT COUNT(*) FROM historical_date_ranges")
                historical_counts["historical_date_ranges"] = cursor.fetchone()[0]
            except sqlite3.OperationalError as e:
                logger.warning(f"Unable to count historical routes: {str(e)}")
                historical_counts["historical_date_ranges"] = 0
                
            conn.close()
        else:
            historical_counts["historical_date_ranges"] = 0
            
        # Get last update time (if available)
        last_update = None
        log_file = "data_updates.log"
        if os.path.exists(log_file):
            try:
                with open(log_file, "r") as f:
                    lines = f.readlines()
                    for line in reversed(lines):
                        if "successfully" in line.lower() and "data" in line.lower():
                            last_update = line.split(" - ")[0]
                            break
            except Exception as e:
                logger.error(f"Error reading update log: {str(e)}")
        
        return jsonify({
            "status": "online",
            "table_counts": table_counts,
            "historical_counts": historical_counts,
            "last_update": last_update
        })
    except Exception as e:
        logger.error(f"Error checking database status: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

def run_scheduled_update():
    """Run scheduled updates for ferry data."""
    while True:
        try:
            # Run update at 3 AM
            current_hour = datetime.now().hour
            if current_hour == 3:
                logger.info("Running scheduled ferry data update")
                subprocess.run(["python", "data_updater.py"], check=True)
                # Sleep for 1 hour after running to avoid multiple executions
                time.sleep(3600)
            else:
                # Check every 15 minutes
                time.sleep(900)
        except Exception as e:
            logger.error(f"Error in scheduled update: {str(e)}")
            time.sleep(900)  # Sleep for 15 minutes on error

# Start update scheduler thread
update_thread = threading.Thread(target=run_scheduled_update, daemon=True)
update_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
