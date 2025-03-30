"""
Route Finding Agent - Specialized agent for finding ferry routes between locations.

This agent focuses exclusively on finding routes between locations, with optimized
prompts for route discovery and integrated historical route checking.
"""

import os
import logging
import sqlite3
from typing import Dict, List, Optional, Any, Tuple
import re
import json

import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.memory import ConversationBufferMemory
from langchain_core.messages import AIMessage, HumanMessage

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get API key from environment variable
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set")

# Database paths
MAIN_DB_PATH = 'gtfs.db'
HISTORICAL_DB_PATH = 'previous_db.db'

class RouteAgent:
    """
    A specialized agent that focuses on finding ferry routes between locations.
    """
    
    def __init__(self):
        """
        Initialize the RouteAgent with specialized route finding capabilities.
        """
        # Configure the Gemini model
        genai.configure(api_key=API_KEY)
        
        # Set up the LLM
        self.llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro")
        
        # Session conversations
        self.conversations = {}
        
        # Create tools for the agent
        self.tools = [
            {
                "name": "run_route_query",
                "description": "Execute an SQL query against the ferry database to find routes",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The SQL query to execute"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "check_historical_routes",
                "description": "Check historical data for routes between ports",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "origin_port": {
                            "type": "string",
                            "description": "The origin port name"
                        },
                        "destination_port": {
                            "type": "string",
                            "description": "The destination port name"
                        }
                    },
                    "required": ["origin_port", "destination_port"]
                }
            }
        ]
        
        # Set up the agent prompt
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", self._get_system_prompt()),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
        ])
        
        # Create the agent
        self.agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=self.prompt
        )
        
        # Set up the agent executor
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=[self.run_route_query, self.check_historical_routes],
            verbose=True
        )
        
        logger.info("Route Agent initialized successfully")
    
    def _get_system_prompt(self) -> str:
        """
        Returns the specialized system prompt for the route finding agent.
        """
        return """
        You are a Route Specialist for FerriesinGreece, focusing exclusively on finding ferry routes between locations.

        MAIN RESPONSIBILITIES:
        - Find direct routes between two specified locations
        - Check for connecting routes when direct routes aren't available
        - Always check historical data when current routes aren't found
        - Provide comprehensive route details (times, durations, vessels)

        DATABASE STRUCTURE:
        - Main DB (gtfs.db): Current routes with the 'routes' table containing:
          route_id, company, origin_port_name, destination_port_name, departure_time, arrival_time, duration
        
        - Historical DB (previous_db.db): Past route data with 'historical_date_ranges' containing:
          origin_code, origin_name, destination_code, destination_name, start_date, end_date, appear_date

        IMPORTANT WORKFLOW:
        1. ALWAYS first search for direct routes in the main database
        2. If no direct routes found, check for connecting routes with ONE intermediate stop
        3. If no current routes exist, ALWAYS check historical data using the check_historical_routes tool
        4. Begin historical responses with: "I couldn't find any current ferry routes from [Origin] to [Destination]. Let me check historical data..."

        RESPONSE FORMAT:
        - For direct routes: List company, departure time, arrival time, and duration
        - For connections: Clearly show each leg of the journey with waiting times
        - For historical data: Indicate when routes operated previously and might be available again

        PORT NAMES:
        - For Athens, check Lavrio, Rafina, and Piraeus ports
        - DB values are in CAPITAL LETTERS, use case-insensitive queries (LOWER())
        - Handle spelling variations and partial matches when possible
        """
    
    def run_route_query(self, query: str) -> str:
        """
        Execute an SQL query against the ferry database.
        
        Args:
            query: SQL query to execute
            
        Returns:
            Query results or error message
        """
        try:
            logger.info(f"Executing query: {query}")
            conn = sqlite3.connect(MAIN_DB_PATH)
            cursor = conn.cursor()
            cursor.execute(query)
            results = cursor.fetchall()
            conn.close()
            
            if not results:
                return "No results found for the given query."
            
            # Return the results as a string
            return str(results)
        except Exception as e:
            logger.error(f"Error executing query: {str(e)}")
            return f"Error executing query: {str(e)}"
    
    def check_historical_routes(self, origin_port: str, destination_port: str) -> str:
        """
        Check historical data for routes between the given ports.
        
        Args:
            origin_port: The name of the departure port
            destination_port: The name of the arrival port
            
        Returns:
            Information about historical routes if found
        """
        logger.info(f"Checking historical routes from {origin_port} to {destination_port}")
        
        # Clean and prepare port names for search
        origin_clean = origin_port.lower().strip()
        destination_clean = destination_port.lower().strip()
        
        try:
            conn = sqlite3.connect(HISTORICAL_DB_PATH)
            cursor = conn.cursor()
            
            # First try exact match
            cursor.execute("""
                SELECT * FROM historical_date_ranges 
                WHERE LOWER(origin_name) = ? AND LOWER(destination_name) = ?
            """, (origin_clean, destination_clean))
            results = cursor.fetchall()
            
            # If no results, try with LIKE for more flexible matching
            if not results:
                logger.info(f"No exact matches, trying pattern matching")
                cursor.execute("""
                    SELECT * FROM historical_date_ranges 
                    WHERE LOWER(origin_name) LIKE ? AND LOWER(destination_name) LIKE ?
                """, (f"%{origin_clean}%", f"%{destination_clean}%"))
                results = cursor.fetchall()
                
                # If still no results, try reverse direction
                if not results:
                    logger.info(f"Trying reverse direction")
                    cursor.execute("""
                        SELECT * FROM historical_date_ranges 
                        WHERE LOWER(origin_name) LIKE ? AND LOWER(destination_name) LIKE ?
                    """, (f"%{destination_clean}%", f"%{origin_clean}%"))
                    results = cursor.fetchall()
            
            conn.close()
            
            if not results:
                return f"No historical routes found between {origin_port} and {destination_port}."
            
            # Format the historical data into a readable response
            response = f"I found historical route information for {origin_port} to {destination_port}:\n\n"
            
            for row in results:
                # Parse dates from the database
                start_date = row[5] if len(row) > 5 else "unknown"
                end_date = row[6] if len(row) > 6 else "unknown"
                appear_date = row[7] if len(row) > 7 else "unknown"
                
                # Add origin and destination
                orig_name = row[2] if len(row) > 2 else origin_port
                dest_name = row[4] if len(row) > 4 else destination_port
                
                response += f"Route: {orig_name} to {dest_name}\n"
                response += f"Operational period: {start_date} to {end_date}\n"
                response += f"First appeared in schedules: {appear_date}\n\n"
            
            response += "This route has operated in the past and might be available again during similar periods or seasons."
            return response
            
        except Exception as e:
            logger.error(f"Error checking historical routes: {str(e)}")
            return f"Error checking historical routes: {str(e)}"
    
    def find_route(self, origin: str, destination: str, date: Optional[str] = None) -> str:
        """
        Find routes between two locations with optional date specification.
        
        Args:
            origin: The departure location
            destination: The arrival location
            date: Optional travel date in YYYY-MM-DD format
            
        Returns:
            Information about available routes
        """
        query = f"Find ferry routes from {origin} to {destination}"
        if date:
            query += f" on {date}"
        
        # Create a unique conversation ID
        conversation_id = f"{origin}_{destination}_{date}"
        
        return self.query(query, conversation_id)
    
    def find_connecting_routes(self, origin: str, destination: str, date: Optional[str] = None) -> str:
        """
        Find connecting routes between locations that don't have direct routes.
        
        Args:
            origin: The departure location
            destination: The arrival location
            date: Optional travel date in YYYY-MM-DD format
            
        Returns:
            Information about connecting routes
        """
        query = f"Find connecting routes from {origin} to {destination}"
        if date:
            query += f" on {date}"
        
        # Create a unique conversation ID
        conversation_id = f"connect_{origin}_{destination}_{date}"
        
        return self.query(query, conversation_id)
    
    def query(self, input_text: str, session_id: str = 'default') -> str:
        """
        Process user queries with conversational context.
        
        Args:
            input_text: User's input query
            session_id: Unique identifier for the chat session
            
        Returns:
            Agent's response
        """
        logger.info(f"Received query: '{input_text}' for session_id: {session_id}")
        
        # Initialize conversation history if it doesn't exist
        if session_id not in self.conversations:
            logger.info(f"Initializing new chat history for session: {session_id}")
            self.conversations[session_id] = []
        
        # Get conversation history
        chat_history = self.conversations[session_id]
        logger.info(f"Current history length: {len(chat_history)}")
        
        # Check if this is a direct route query (e.g., "Brindisi to Corfu")
        direct_route_pattern = r"^([A-Za-z\s\(\)]+)\s+to\s+([A-Za-z\s\(\)]+)$"
        route_match = re.match(direct_route_pattern, input_text)
        
        if route_match:
            # This is a direct route query, extract the origin and destination
            origin = route_match.group(1).strip()
            destination = route_match.group(2).strip()
            logger.info(f"Detected direct route query: {origin} to {destination}")
            
            # First check for direct routes
            direct_query = f"""
            SELECT route_number, company, origin_port_name, destination_port_name, 
                   departure_time, arrival_time, duration 
            FROM routes 
            WHERE LOWER(origin_port_name) = LOWER('{origin}') 
              AND LOWER(destination_port_name) = LOWER('{destination}')
            """
            
            direct_results = self.run_route_query(direct_query)
            
            if "No results found" in direct_results:
                # If no direct routes, check for connecting routes
                logger.info(f"No direct routes found, checking for connecting routes")
                
                # Build a more sophisticated prompt for the agent
                connecting_prompt = f"Find connecting routes from {origin} to {destination} with one stopover or connection"
                
                # Run the agent with the connecting prompt
                result = self.agent_executor.invoke({
                    "input": connecting_prompt,
                    "chat_history": chat_history
                })
                
                # Update chat history
                chat_history.append(HumanMessage(content=input_text))
                chat_history.append(AIMessage(content=result["output"]))
                
                # Return the response
                return result["output"]
            else:
                # Use the agent to format the direct results nicely
                result = self.agent_executor.invoke({
                    "input": input_text,
                    "chat_history": chat_history
                })
                
                # Update chat history
                chat_history.append(HumanMessage(content=input_text))
                chat_history.append(AIMessage(content=result["output"]))
                
                return result["output"]
        
        # For any other type of query, use the regular agent flow
        logger.info("Invoking agent executor")
        result = self.agent_executor.invoke({
            "input": input_text,
            "chat_history": chat_history
        })
        
        logger.info(f"Agent result type: {type(result)}")
        logger.info(f"Agent result keys: {result.keys()}")
        logger.info(f"Agent response length: {len(result['output'])}")
        
        # Update conversation history
        chat_history.append(HumanMessage(content=input_text))
        chat_history.append(AIMessage(content=result["output"]))
        
        # Make sure we don't keep the history too long
        if len(chat_history) > 10:
            # Keep the last 10 messages
            self.conversations[session_id] = chat_history[-10:]
        
        logger.info("Agent response generated successfully")
        return result["output"]


# For testing
if __name__ == "__main__":
    route_agent = RouteAgent()
    print(route_agent.find_route("Piraeus", "Mykonos"))
    print(route_agent.find_connecting_routes("Brindisi", "Corfu"))