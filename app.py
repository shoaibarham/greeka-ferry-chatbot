import os
import logging
import sqlite3
from datetime import datetime
import subprocess
import threading
import time

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash

# Initialize logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")

# Configure SQLAlchemy
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///ferry_system.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database paths
DB_PATH = 'gtfs.db'
HISTORICAL_DB_PATH = 'previous_db.db'

# Initialize ferry agent (outside the routes to avoid recreation on each request)
ferry_agent = None

def initialize_databases():
    """Initialize both the main and historical databases if needed."""
    # Initialize main database
    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0:
        logger.info("Initializing main ferry database...")
        try:
            import initialize_data
            initialize_data.main()
            logger.info("Main database initialization complete")
        except Exception as e:
            logger.error(f"Failed to initialize main database: {str(e)}")
            raise
    
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

# Set up the database
from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy(app)

# Initialize the database tables (after SQLAlchemy is set up)
with app.app_context():
    from models import User, FerryCompany, Port, Vessel, Accommodation, FerryRoute, Schedule
    db.create_all()

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    """Load a user from the database by ID."""
    from models import User
    try:
        return User.query.get(int(user_id))
    except Exception as e:
        logger.error(f"Error loading user: {str(e)}")
        return None

# Create admin user if it doesn't exist
def create_admin_user():
    """Create an admin user if one doesn't exist."""
    from models import User
    
    try:
        # Check if any admin users exist
        admin_exists = User.query.filter_by(is_admin=True).first() is not None
        
        if not admin_exists:
            # Create default admin user
            admin = User(
                username="admin",
                email="admin@ferrysystem.com",
                is_admin=True
            )
            admin.set_password("ferry_admin_2025")  # Default password, should be changed
            
            db.session.add(admin)
            db.session.commit()
            
            logger.info("Created default admin user")
    except Exception as e:
        logger.error(f"Error creating admin user: {str(e)}")

# Initialize the default admin user
create_admin_user()

# Initialize the ferry agent at app startup
initialize_agent()

# Routes
@app.route("/")
def index():
    """Render the home page with navigation options."""
    return render_template("home.html")

@app.route("/ferry-chat")
def ferry_chat():
    """Render the main page of the ferry chatbot application."""
    return render_template("index.html")

@app.route("/admin")
@login_required
def admin():
    """Render the admin panel for managing ferry data."""
    if not current_user.is_admin:
        flash("Admin privileges required to access this page.", "danger")
        return redirect(url_for("index"))
    return render_template("admin.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Handle user login."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))
        
    if request.method == "POST":
        from models import User
        
        username = request.form.get("username")
        password = request.form.get("password")
        
        user = db.session.query(User).filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash("Logged in successfully.", "success")
            
            # Redirect to the page the user was trying to access
            next_page = request.args.get("next")
            if not next_page or next_page.startswith('/'):
                next_page = url_for("index")
            return redirect(next_page)
        else:
            flash("Invalid username or password. Please try again.", "danger")
    
    return render_template("login.html")
    
@app.route("/logout")
@login_required
def logout():
    """Handle user logout."""
    logout_user()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("index"))
    
@app.route("/register", methods=["GET", "POST"])
def register():
    """Handle user registration."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))
        
    if request.method == "POST":
        from models import User
        
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        password_confirm = request.form.get("password_confirm")
        
        # Validate inputs
        error = None
        if not username:
            error = "Username is required."
        elif not email:
            error = "Email address is required."
        elif not password:
            error = "Password is required."
        elif password != password_confirm:
            error = "Passwords do not match."
        elif db.session.query(User).filter_by(username=username).first() is not None:
            error = f"Username {username} is already taken."
        elif db.session.query(User).filter_by(email=email).first() is not None:
            error = f"Email {email} is already registered."
            
        if error is None:
            # Create new user
            new_user = User(
                username=username,
                email=email
            )
            new_user.set_password(password)
            
            db.session.add(new_user)
            db.session.commit()
            
            flash("Your account has been created successfully! You can now log in.", "success")
            return redirect(url_for("login"))
        else:
            flash(error, "danger")
    
    return render_template("register.html")

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
        result = sqlite_loader.load_data(source_file)
        return jsonify({"success": True, "message": result})
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
