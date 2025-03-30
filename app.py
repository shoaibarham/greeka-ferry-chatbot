import os
import logging
import sqlite3
from datetime import datetime
import subprocess
import threading
import time
import re
import traceback

from flask import Flask, render_template, request, jsonify, session

# Initialize logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")

# Database paths
DB_PATH = 'gtfs.db'
HISTORICAL_DB_PATH = 'previous_db.db'

# Initialize agents
ferry_agent = None
agent_manager = None

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
            
            # Check if the API key is set
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                logger.error("GEMINI_API_KEY environment variable not set")
                raise RuntimeError("API key not set. Please ensure that GEMINI_API_KEY is set in the environment variables.")
            
            ferry_agent = FerryAgent()
            logger.info("Ferry agent initialized successfully")
        except RuntimeError as e:
            logger.error(f"API key error when initializing ferry agent: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize ferry agent: {str(e)}")
            logger.error(traceback.format_exc())
            raise

def initialize_agent_manager():
    """Initialize the agent manager if not already initialized."""
    global agent_manager
    if agent_manager is None:
        try:
            # Make sure databases are initialized first
            initialize_databases()
            
            # Check if the API key is set
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                logger.error("GEMINI_API_KEY environment variable not set")
                raise RuntimeError("API key not set. Please ensure that GEMINI_API_KEY is set in the environment variables.")
            
            # Import and initialize the agent manager
            from agents.agent_manager import get_agent_manager
            agent_manager = get_agent_manager()
            logger.info("Agent manager initialized successfully")
        except RuntimeError as e:
            logger.error(f"API key error when initializing agent manager: {str(e)}")
            # We should still raise this so the app can fall back to ferry_agent
            # Don't try to initialize ferry_agent here as it will also fail with the same error
            raise
        except Exception as e:
            logger.error(f"Failed to initialize agent manager: {str(e)}")
            logger.error(traceback.format_exc())
            # Fall back to the main ferry agent, but only if it's not an API key error
            # as that would fail too
            raise

# Initialize the agents at app startup
try:
    initialize_agent_manager()
except Exception as e:
    logger.error(f"Failed to initialize agent manager, falling back to main ferry agent: {str(e)}")
    initialize_agent()

# Routes
@app.route("/")
def index():
    """Render the main page of the ferry chatbot application."""
    return render_template("index.html")

@app.route("/admin")
def admin():
    """Render the admin panel for managing ferry data."""
    return render_template("admin.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Process user queries and return AI-generated responses using the appropriate agent.
    """
    try:
        # Get user message
        data = request.json
        user_message = data.get("message", "")
        conversation_id = data.get("conversation_id", None)
        agent_type = data.get("agent_type", "auto")  # Get selected agent type
        
        # Initialize or retrieve conversation history
        if not conversation_id:
            conversation_id = datetime.now().strftime("%Y%m%d%H%M%S")
            session[conversation_id] = []
        
        # Try to use the agent manager if available
        if agent_manager is not None:
            logger.info(f"Processing query with agent manager: '{user_message}' (session: {conversation_id}, agent: {agent_type})")
            
            try:
                # Handle specific agent types
                if agent_type == "route":
                    logger.info("Using Route Finding Agent directly")
                    try:
                        response = agent_manager.route_agent.query(user_message, conversation_id)
                    except RuntimeError as e:
                        logger.error(f"Route agent initialization error: {str(e)}")
                        if "API key" in str(e):
                            response = f"I'm sorry, but there's an issue with the API configuration. Please ensure that a valid Gemini API key is set in the environment."
                        else:
                            response = f"I'm sorry, but I'm currently experiencing technical difficulties with the route finding service. Please try again in a few moments or contact support if the issue persists."
                elif agent_type == "price":
                    logger.info("Using Price Comparison Agent directly")
                    try:
                        response = agent_manager.price_agent.query(user_message, conversation_id)
                    except RuntimeError as e:
                        logger.error(f"Price agent initialization error: {str(e)}")
                        if "API key" in str(e):
                            response = f"I'm sorry, but there's an issue with the API configuration. Please ensure that a valid Gemini API key is set in the environment."
                        else:
                            response = f"I'm sorry, but I'm currently experiencing technical difficulties with the price comparison service. Please try again in a few moments or contact support if the issue persists."
                elif agent_type == "schedule":
                    logger.info("Using Schedule Optimization Agent directly")
                    try:
                        response = agent_manager.schedule_agent.query(user_message, conversation_id)
                    except RuntimeError as e:
                        logger.error(f"Schedule agent initialization error: {str(e)}")
                        if "API key" in str(e):
                            response = f"I'm sorry, but there's an issue with the API configuration. Please ensure that a valid Gemini API key is set in the environment."
                        else:
                            response = f"I'm sorry, but I'm currently experiencing technical difficulties with the schedule optimization service. Please try again in a few moments or contact support if the issue persists."
                elif agent_type == "travel":
                    logger.info("Using Travel Planning Agent directly")
                    try:
                        response = agent_manager.travel_agent.query(user_message, conversation_id)
                    except RuntimeError as e:
                        logger.error(f"Travel agent initialization error: {str(e)}")
                        if "API key" in str(e):
                            response = f"I'm sorry, but there's an issue with the API configuration. Please ensure that a valid Gemini API key is set in the environment."
                        else:
                            response = f"I'm sorry, but I'm currently experiencing technical difficulties with the travel planning service. Please try again in a few moments or contact support if the issue persists."
                else:
                    # Auto-detect or fallback
                    response = agent_manager.process_query(user_message, conversation_id)
            except Exception as e:
                logger.error(f"Error with agent processing: {str(e)}")
                # Fall back to the main ferry agent
                try:
                    if ferry_agent is None:
                        initialize_agent()
                    response = ferry_agent.query(user_message, conversation_id)
                except Exception as e:
                    logger.error(f"Fallback agent also failed: {str(e)}")
                    if "API key" in str(e):
                        response = "I'm sorry, but there's an issue with the API configuration. Please ensure that a valid Gemini API key is set in the environment."
                    else:
                        response = "I'm sorry, but I'm experiencing technical difficulties connecting to the ferry information service. Please try again later."
        else:
            # Fall back to the main ferry agent
            logger.info(f"Agent manager not available, using main ferry agent")
            # Make sure agent is initialized
            try:
                if ferry_agent is None:
                    initialize_agent()
                
                # Check if this is a direct route query (e.g., "Brindisi to Corfu")
                direct_route_pattern = r"^([A-Za-z\s\(\)]+)\s+to\s+([A-Za-z\s\(\)]+)$"
                route_match = re.match(direct_route_pattern, user_message)
                
                if route_match:
                    # This appears to be a direct route query, let's handle it specially
                    origin = route_match.group(1).strip()
                    destination = route_match.group(2).strip()
                    logger.info(f"Detected direct route query: {origin} to {destination}")
                    
                    try:
                        # First check for direct routes using a safe query through the ferry agent
                        route_query = f"""
                        SELECT route_number, company, origin_port_name, destination_port_name, 
                               departure_time, arrival_time, duration 
                        FROM routes 
                        WHERE LOWER(origin_port_name) = LOWER('{origin}') 
                          AND LOWER(destination_port_name) = LOWER('{destination}')
                        """
                        
                        # Get direct routes
                        route_results = ferry_agent.run_ferry_query(route_query)
                        
                        if "No results found" in route_results or not route_results:
                            # If no current routes, check historical data directly
                            logger.info(f"No current routes found, checking historical data for {origin} to {destination}")
                            try:
                                historical_results = ferry_agent.check_historical_routes(origin, destination)
                                
                                if "No historical routes found" in historical_results:
                                    response = f"I couldn't find any current ferry routes from {origin} to {destination}. " \
                                              f"Let me check the historical data...\n\n" \
                                              f"I don't have any historical records of routes between {origin} and {destination}. " \
                                              f"This route may not be offered by any ferry company, or it might require a connection " \
                                              f"through another port."
                                else:
                                    response = f"I couldn't find any current ferry routes from {origin} to {destination}. " \
                                              f"Let me check the historical data...\n\n{historical_results}"
                            except Exception as e:
                                logger.error(f"Error checking historical routes: {str(e)}")
                                response = f"I couldn't find any current ferry routes from {origin} to {destination}. " \
                                          f"I also encountered an issue while checking historical data. Please try again later."
                        else:
                            # Let the agent handle the response for proper formatting
                            response = ferry_agent.query(user_message, conversation_id)
                    except Exception as e:
                        logger.error(f"Error processing direct route query: {str(e)}")
                        response = f"I'm sorry, but I encountered an issue while searching for routes between {origin} and {destination}. " \
                                  f"Please try again later or contact support if the problem persists."
                else:
                    # Process the query with ferry agent normally
                    response = ferry_agent.query(user_message, conversation_id)
            except Exception as e:
                logger.error(f"Error with ferry agent: {str(e)}")
                if "API key" in str(e):
                    response = "I'm sorry, but there's an issue with the API configuration. Please ensure that a valid Gemini API key is set in the environment."
                else:
                    response = "I'm sorry, but I'm experiencing technical difficulties connecting to the ferry information service. Please try again later."
        
        # Return response to frontend
        return jsonify({
            "response": response,
            "conversation_id": conversation_id,
            "agent_used": agent_type
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
        
        # Reinitialize agents after data update
        global ferry_agent, agent_manager
        ferry_agent = None
        agent_manager = None
        
        # Try to initialize agent manager first
        try:
            initialize_agent_manager()
        except Exception as e:
            logger.error(f"Failed to reinitialize agent manager: {str(e)}")
            initialize_agent()
        
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
        
        # Reinitialize agents after data update
        global ferry_agent, agent_manager
        ferry_agent = None
        agent_manager = None
        
        # Try to initialize agent manager first
        try:
            initialize_agent_manager()
        except Exception as e:
            logger.error(f"Failed to reinitialize agent manager: {str(e)}")
            initialize_agent()
        
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
        
        # Use ferry_agent (which should always be available or can fall back to)
        try:
            if ferry_agent is None:
                initialize_agent()
                
            port_info = ferry_agent.get_port_information(search_term)
            # Split the port info string into a list of ports
            ports = [{"code": line.split(":")[0].strip(), "name": line.split(":")[1].strip()} 
                     for line in port_info.split("\n") if ":" in line]
            return jsonify({"ports": ports})
        except RuntimeError as e:
            logger.error(f"Ferry agent initialization error: {str(e)}")
            if "API key" in str(e):
                return jsonify({
                    "error": "API configuration issue",
                    "message": "There appears to be an issue with the API configuration. Please ensure that a valid Gemini API key is set in the environment."
                }), 503
            else:
                return jsonify({
                    "error": "Failed to initialize ferry information service",
                    "message": "The system is currently experiencing technical difficulties. Please try again later."
                }), 503
    except Exception as e:
        logger.error(f"Error retrieving ports: {str(e)}")
        return jsonify({
            "error": "Failed to retrieve port information",
            "message": "There was an error processing your request. Please try again later."
        }), 500

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
        
        # Check agent status
        agent_status = {
            "main_ferry_agent": ferry_agent is not None,
            "agent_manager": agent_manager is not None,
            "specialized_agents": []
        }
        
        # Check which specialized agents are initialized
        if agent_manager is not None:
            # Check route agent
            if hasattr(agent_manager, '_route_agent') and agent_manager._route_agent is not None:
                agent_status["specialized_agents"].append("route_agent")
            
            # Check price agent
            if hasattr(agent_manager, '_price_agent') and agent_manager._price_agent is not None:
                agent_status["specialized_agents"].append("price_agent")
            
            # Check schedule agent
            if hasattr(agent_manager, '_schedule_agent') and agent_manager._schedule_agent is not None:
                agent_status["specialized_agents"].append("schedule_agent")
            
            # Check travel agent
            if hasattr(agent_manager, '_travel_agent') and agent_manager._travel_agent is not None:
                agent_status["specialized_agents"].append("travel_agent")
        
        return jsonify({
            "status": "online",
            "table_counts": table_counts,
            "historical_counts": historical_counts,
            "agent_status": agent_status,
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