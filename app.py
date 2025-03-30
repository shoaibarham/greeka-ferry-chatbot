import os
import logging
from datetime import datetime

from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Initialize logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create Flask app
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")

# Configure database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///ferry_data.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize database
db.init_app(app)

# Initialize app context
with app.app_context():
    # Import models after initializing app
    from models import FerryRoute, FerryCompany, Port, Vessel, Schedule, Accommodation
    db.create_all()

# Routes
@app.route("/")
def index():
    """Render the main page of the ferry chatbot application."""
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Process user queries and return AI-generated responses
    using the Gemini model and LangChain agents.
    """
    from config import GEMINI_API_KEY
    from langchain.callbacks.manager import CallbackManager
    from langchain.chat_models import ChatGoogleGenerativeAI
    from langchain.agents import initialize_agent, AgentType
    from prompts.system_prompt import get_system_prompt
    from tools.ferry_tools import get_tools

    try:
        # Get user message
        data = request.json
        user_message = data.get("message", "")
        conversation_id = data.get("conversation_id", None)
        
        # Initialize or retrieve conversation history
        if not conversation_id:
            conversation_id = datetime.now().strftime("%Y%m%d%H%M%S")
            session[conversation_id] = []
        
        conversation_history = session.get(conversation_id, [])
        
        # Set up the LLM with Gemini
        llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.1,
            google_api_key=GEMINI_API_KEY,
            convert_system_message_to_human=True
        )
        
        # Set up tools for structured data retrieval
        tools = get_tools()
        
        # Initialize the agent
        agent = initialize_agent(
            tools=tools,
            llm=llm,
            agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True
        )
        
        # Get system prompt
        system_prompt = get_system_prompt()
        
        # Create input for agent
        agent_input = {
            "input": user_message,
            "chat_history": conversation_history,
            "system_prompt": system_prompt
        }
        
        # Execute agent to get response
        result = agent.run(agent_input)
        
        # Update conversation history
        conversation_history.append({"role": "user", "content": user_message})
        conversation_history.append({"role": "assistant", "content": result})
        session[conversation_id] = conversation_history
        
        # Return response to frontend
        return jsonify({
            "response": result,
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
    Endpoint to trigger data update process.
    This would typically be called by a scheduled task.
    """
    from data_processor import update_ferry_data
    
    try:
        source_file = request.json.get("source_file", "GTFS_data_v5.json")
        result = update_ferry_data(source_file)
        return jsonify({"success": True, "message": result})
    except Exception as e:
        logger.error(f"Error updating ferry data: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to update ferry data",
            "details": str(e)
        }), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
