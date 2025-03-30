"""
Schedule Optimization Agent - Specialized agent for finding optimal travel times.

This agent helps users find optimal travel schedules, suggests alternative routes
with better timing, and considers transfer times for multi-leg journeys.
"""

import os
import logging
import sqlite3
from typing import Dict, List, Optional, Any, Tuple
import re
import json
import datetime

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

class ScheduleAgent:
    """
    A specialized agent that helps users find optimal ferry schedules.
    """
    
    def __init__(self):
        """
        Initialize the ScheduleAgent with specialized schedule optimization capabilities.
        """
        try:
            # Configure the Gemini model
            genai.configure(api_key=API_KEY)
            
            # Set up the LLM with a timeout
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-1.5-pro",
                timeout=30.0,  # 30 seconds timeout
                max_retries=2
            )
        except Exception as e:
            logger.error(f"Failed to initialize Gemini LLM: {str(e)}")
            raise RuntimeError(f"Could not initialize Gemini API: {str(e)}")
        
        # Session conversations
        self.conversations = {}
        
        # Create tools for the agent
        self.tools = [
            {
                "name": "run_schedule_query",
                "description": "Execute an SQL query against the ferry database to find schedule information",
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
                "name": "find_optimal_schedule",
                "description": "Find the optimal schedule between two locations",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "origin": {
                            "type": "string",
                            "description": "The origin port or location"
                        },
                        "destination": {
                            "type": "string",
                            "description": "The destination port or location"
                        },
                        "date": {
                            "type": "string",
                            "description": "Optional travel date in YYYY-MM-DD format"
                        },
                        "preference": {
                            "type": "string",
                            "description": "Schedule preference (earliest, latest, shortest)",
                            "enum": ["earliest", "latest", "shortest"]
                        }
                    },
                    "required": ["origin", "destination"]
                }
            },
            {
                "name": "find_connecting_schedule",
                "description": "Find connecting schedules for multi-leg journeys",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "origin": {
                            "type": "string",
                            "description": "The origin port or location"
                        },
                        "destination": {
                            "type": "string",
                            "description": "The destination port or location"
                        },
                        "date": {
                            "type": "string",
                            "description": "Optional travel date in YYYY-MM-DD format"
                        },
                        "min_transfer_time": {
                            "type": "integer",
                            "description": "Minimum transfer time in minutes (default 60)"
                        }
                    },
                    "required": ["origin", "destination"]
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
            tools=[
                self.run_schedule_query, 
                self.find_optimal_schedule, 
                self.find_connecting_schedule
            ],
            verbose=True
        )
        
        logger.info("Schedule Agent initialized successfully")
    
    def _get_system_prompt(self) -> str:
        """
        Returns the specialized system prompt for the schedule optimization agent.
        """
        return """
        You are a Schedule Specialist for FerriesinGreece, focusing exclusively on helping users find optimal ferry schedules.

        MAIN RESPONSIBILITIES:
        - Find the earliest, latest, or fastest ferry schedules between locations
        - Suggest alternative routes with better timing
        - Create efficient multi-leg journeys with reasonable transfer times
        - Consider seasonal variations in schedules

        DATABASE STRUCTURE:
        - Main DB (gtfs.db) contains the following relevant tables:
        
          1. routes: Contains route and schedule information
             Fields: route_id, company, origin_port_name, destination_port_name,
                    departure_time, arrival_time, duration (in minutes)
          
          2. dates_and_vessels: Links routes to specific dates
             Fields: route_id, schedule_date, vessel

        IMPORTANT SCHEDULING CONSIDERATIONS:
        - Always ensure sufficient transfer time for connecting routes (at least 1 hour)
        - When optimizing for "earliest arrival", consider the total journey time, not just departure time
        - When optimizing for "latest departure", ensure arrival is still on the same day if possible
        - Consider the duration of the journey when suggesting routes
        - Times are stored in 24-hour format (HH:MM)

        RESPONSE FORMAT:
        - Show time information clearly with departure and arrival times
        - Display duration in hours and minutes
        - For connections, clearly show each leg with waiting time between ferries
        - Group routes by preference (earliest, latest, shortest) when multiple options exist
        - Indicate when a route requires an overnight stay
        
        SEARCH TIPS:
        - For Athens, check schedules from Lavrio, Rafina, and Piraeus ports
        - DB values are in CAPITAL LETTERS, use case-insensitive queries (LOWER())
        - For seasonal routes, check the dates_and_vessels table for availability
        """
    
    def run_schedule_query(self, query: str) -> str:
        """
        Execute an SQL query against the ferry database to find schedule information.
        
        Args:
            query: SQL query to execute
            
        Returns:
            Query results or error message
        """
        try:
            logger.info(f"Executing schedule query: {query}")
            conn = sqlite3.connect(MAIN_DB_PATH)
            cursor = conn.cursor()
            cursor.execute(query)
            results = cursor.fetchall()
            conn.close()
            
            if not results:
                return "No schedule results found for the given query."
            
            # Return the results as a string
            return str(results)
        except Exception as e:
            logger.error(f"Error executing schedule query: {str(e)}")
            return f"Error executing schedule query: {str(e)}"
    
    def find_optimal_schedule(self, origin: str, destination: str, date: Optional[str] = None, preference: str = "earliest") -> str:
        """
        Find the optimal schedule between two locations based on specified preferences.
        
        Args:
            origin: The origin port or location
            destination: The destination port or location
            date: Optional travel date in YYYY-MM-DD format
            preference: Schedule preference (earliest, latest, shortest)
            
        Returns:
            Optimal schedule information
        """
        logger.info(f"Finding optimal schedule from {origin} to {destination}, preference: {preference}")
        
        # Check if the origin is Athens, which requires checking multiple ports
        is_athens = origin.lower() in ['athens', 'athina', 'αθήνα', 'αθηνα']
        
        try:
            conn = sqlite3.connect(MAIN_DB_PATH)
            cursor = conn.cursor()
            
            # Build the appropriate query based on preference
            if preference == "earliest":
                # Find routes with earliest arrival time
                order_clause = "r.departure_time ASC, r.arrival_time ASC"
            elif preference == "latest":
                # Find routes with latest departure time but still arriving on the same day
                order_clause = "r.departure_time DESC"
            elif preference == "shortest":
                # Find routes with shortest duration
                order_clause = "r.duration ASC"
            else:
                # Default to earliest departure
                order_clause = "r.departure_time ASC"
            
            if is_athens:
                # For Athens, check schedules from all three major ports
                logger.info("Searching Athens ports (Piraeus, Rafina, Lavrio)")
                
                # Base query for Athens
                query = f"""
                SELECT 
                    r.origin_port_name, 
                    r.destination_port_name, 
                    r.company, 
                    r.departure_time,
                    r.arrival_time,
                    r.duration,
                    r.route_id
                FROM 
                    routes r
                WHERE 
                    LOWER(r.origin_port_name) IN ('piraeus', 'rafina', 'lavrio')
                    AND LOWER(r.destination_port_name) LIKE LOWER(?)
                """
                
                # Add date filter if specified
                if date:
                    query += f"""
                    AND r.route_id IN (
                        SELECT route_id FROM dates_and_vessels
                        WHERE schedule_date = ?
                    )
                    """
                    query_params = (f'%{destination}%', date)
                else:
                    query_params = (f'%{destination}%',)
                
                # Add ordering
                query += f"ORDER BY {order_clause} LIMIT 5"
                
                if date:
                    cursor.execute(query, query_params)
                else:
                    cursor.execute(query, query_params)
            else:
                # For other origins, search by the specified location
                # Base query
                query = f"""
                SELECT 
                    r.origin_port_name, 
                    r.destination_port_name, 
                    r.company, 
                    r.departure_time,
                    r.arrival_time,
                    r.duration,
                    r.route_id
                FROM 
                    routes r
                WHERE 
                    LOWER(r.origin_port_name) LIKE LOWER(?)
                    AND LOWER(r.destination_port_name) LIKE LOWER(?)
                """
                
                # Add date filter if specified
                if date:
                    query += f"""
                    AND r.route_id IN (
                        SELECT route_id FROM dates_and_vessels
                        WHERE schedule_date = ?
                    )
                    """
                    query_params = (f'%{origin}%', f'%{destination}%', date)
                else:
                    query_params = (f'%{origin}%', f'%{destination}%')
                
                # Add ordering
                query += f"ORDER BY {order_clause} LIMIT 5"
                
                cursor.execute(query, query_params)
            
            results = cursor.fetchall()
            conn.close()
            
            if not results:
                # If no results with the current query, try a more flexible search
                return f"No direct schedules found from {origin} to {destination}" + (f" on {date}" if date else "") + "."
            
            # Format the results into a readable response
            pref_text = {"earliest": "earliest departure", "latest": "latest departure", "shortest": "shortest duration"}
            response = f"Optimal ferry schedules from {origin} to {destination}" + (f" on {date}" if date else "") + f" ({pref_text.get(preference, 'optimal')}):\n\n"
            
            for i, (orig, dest, company, dep_time, arr_time, duration, _) in enumerate(results, 1):
                # Calculate duration in hours and minutes
                hours = duration // 60
                minutes = duration % 60
                duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
                
                response += f"{i}. {orig} to {dest}\n"
                response += f"   Company: {company}\n"
                response += f"   Departure: {dep_time}, Arrival: {arr_time}\n"
                response += f"   Duration: {duration_str}\n\n"
            
            # Add special highlight for the most optimal option based on preference
            if results:
                if preference == "earliest":
                    # Highlight the earliest departure
                    earliest = min(results, key=lambda x: x[3])  # Sort by departure_time
                    response += f"⏰ Earliest option: {earliest[2]} departing at {earliest[3]} from {earliest[0]}\n"
                elif preference == "latest":
                    # Highlight the latest departure
                    latest = max(results, key=lambda x: x[3])  # Sort by departure_time
                    response += f"⏰ Latest option: {latest[2]} departing at {latest[3]} from {latest[0]}\n"
                elif preference == "shortest":
                    # Highlight the shortest duration
                    shortest = min(results, key=lambda x: x[5])  # Sort by duration
                    hrs = shortest[5] // 60
                    mins = shortest[5] % 60
                    dur_str = f"{hrs}h {mins}m" if hrs > 0 else f"{mins}m"
                    response += f"⏰ Fastest option: {shortest[2]} with duration of {dur_str}\n"
            
            return response
            
        except Exception as e:
            logger.error(f"Error finding optimal schedule: {str(e)}")
            return f"Error finding optimal schedule: {str(e)}"
    
    def find_connecting_schedule(self, origin: str, destination: str, date: Optional[str] = None, min_transfer_time: int = 60) -> str:
        """
        Find connecting schedules for multi-leg journeys.
        
        Args:
            origin: The origin port or location
            destination: The destination port or location
            date: Optional travel date in YYYY-MM-DD format
            min_transfer_time: Minimum transfer time in minutes
            
        Returns:
            Connecting schedule information
        """
        logger.info(f"Finding connecting schedule from {origin} to {destination}, min transfer time: {min_transfer_time}min")
        
        try:
            conn = sqlite3.connect(MAIN_DB_PATH)
            cursor = conn.cursor()
            
            # First, check if there's a direct route (for reference)
            direct_query = """
            SELECT 
                r.origin_port_name, 
                r.destination_port_name, 
                r.company, 
                r.departure_time,
                r.arrival_time,
                r.duration
            FROM 
                routes r
            WHERE 
                LOWER(r.origin_port_name) LIKE LOWER(?)
                AND LOWER(r.destination_port_name) LIKE LOWER(?)
            """
            
            if date:
                direct_query += """
                AND r.route_id IN (
                    SELECT route_id FROM dates_and_vessels
                    WHERE schedule_date = ?
                )
                """
                cursor.execute(direct_query, (f'%{origin}%', f'%{destination}%', date))
            else:
                cursor.execute(direct_query, (f'%{origin}%', f'%{destination}%'))
            
            direct_results = cursor.fetchall()
            
            # Get all possible first legs
            first_leg_query = """
            SELECT 
                r.origin_port_name, 
                r.destination_port_name, 
                r.company, 
                r.departure_time,
                r.arrival_time,
                r.duration
            FROM 
                routes r
            WHERE 
                LOWER(r.origin_port_name) LIKE LOWER(?)
            """
            
            if date:
                first_leg_query += """
                AND r.route_id IN (
                    SELECT route_id FROM dates_and_vessels
                    WHERE schedule_date = ?
                )
                """
                cursor.execute(first_leg_query, (f'%{origin}%', date))
            else:
                cursor.execute(first_leg_query, (f'%{origin}%',))
            
            first_legs = cursor.fetchall()
            
            # Get all possible second legs
            second_leg_query = """
            SELECT 
                r.origin_port_name, 
                r.destination_port_name, 
                r.company, 
                r.departure_time,
                r.arrival_time,
                r.duration
            FROM 
                routes r
            WHERE 
                LOWER(r.destination_port_name) LIKE LOWER(?)
            """
            
            if date:
                second_leg_query += """
                AND r.route_id IN (
                    SELECT route_id FROM dates_and_vessels
                    WHERE schedule_date = ?
                )
                """
                cursor.execute(second_leg_query, (f'%{destination}%', date))
            else:
                cursor.execute(second_leg_query, (f'%{destination}%',))
            
            second_legs = cursor.fetchall()
            
            conn.close()
            
            # Find possible connections
            connections = []
            for first in first_legs:
                first_origin, first_dest, first_company, first_dep, first_arr, first_dur = first
                
                for second in second_legs:
                    second_origin, second_dest, second_company, second_dep, second_arr, second_dur = second
                    
                    # Check if the connection is possible
                    if first_dest.lower() == second_origin.lower():
                        # Convert times to minutes for comparison
                        def time_to_minutes(time_str):
                            h, m = map(int, time_str.split(':'))
                            return h * 60 + m
                        
                        first_arr_min = time_to_minutes(first_arr)
                        second_dep_min = time_to_minutes(second_dep)
                        
                        # Check if there's enough transfer time (and second departure is after first arrival)
                        transfer_time = (second_dep_min - first_arr_min) % (24 * 60)  # Handle overnight connections
                        
                        if transfer_time >= min_transfer_time:
                            # This is a valid connection
                            connections.append({
                                'first_leg': first,
                                'second_leg': second,
                                'transfer_time': transfer_time,
                                'total_duration': first_dur + second_dur + transfer_time
                            })
            
            # Sort connections by total duration
            connections.sort(key=lambda x: x['total_duration'])
            
            # Format the results
            if direct_results:
                response = f"I found {len(direct_results)} direct ferry routes from {origin} to {destination}" + (f" on {date}" if date else "") + ":\n\n"
                
                for i, (orig, dest, company, dep_time, arr_time, duration) in enumerate(direct_results[:3], 1):
                    hours = duration // 60
                    minutes = duration % 60
                    duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
                    
                    response += f"{i}. {orig} to {dest} (Direct)\n"
                    response += f"   Company: {company}\n"
                    response += f"   Departure: {dep_time}, Arrival: {arr_time}\n"
                    response += f"   Duration: {duration_str}\n\n"
                
                if connections:
                    response += f"Additionally, I found {len(connections)} connecting routes that might be of interest:\n\n"
            elif connections:
                response = f"I couldn't find direct routes from {origin} to {destination}" + (f" on {date}" if date else "") + f", but I found {len(connections)} connecting options:\n\n"
            else:
                return f"I couldn't find any direct or connecting routes from {origin} to {destination}" + (f" on {date}" if date else "") + "."
            
            # Add connection details (limit to top 3)
            for i, conn in enumerate(connections[:3], 1 if direct_results else 1):
                first = conn['first_leg']
                second = conn['second_leg']
                transfer_time = conn['transfer_time']
                total_duration = conn['total_duration']
                
                # Calculate duration strings
                hours1 = first[5] // 60
                minutes1 = first[5] % 60
                duration_str1 = f"{hours1}h {minutes1}m" if hours1 > 0 else f"{minutes1}m"
                
                hours2 = second[5] // 60
                minutes2 = second[5] % 60
                duration_str2 = f"{hours2}h {minutes2}m" if hours2 > 0 else f"{minutes2}m"
                
                transfer_hours = transfer_time // 60
                transfer_minutes = transfer_time % 60
                transfer_str = f"{transfer_hours}h {transfer_minutes}m" if transfer_hours > 0 else f"{transfer_minutes}m"
                
                total_hours = total_duration // 60
                total_minutes = total_duration % 60
                total_str = f"{total_hours}h {total_minutes}m" if total_hours > 0 else f"{total_minutes}m"
                
                response += f"{i}. {first[0]} → {first[1]} → {second[1]} (Connection)\n"
                response += f"   Leg 1: {first[2]} from {first[0]} to {first[1]}\n"
                response += f"     Departure: {first[3]}, Arrival: {first[4]} (Duration: {duration_str1})\n"
                response += f"   Transfer time in {first[1]}: {transfer_str}\n"
                response += f"   Leg 2: {second[2]} from {second[0]} to {second[1]}\n"
                response += f"     Departure: {second[3]}, Arrival: {second[4]} (Duration: {duration_str2})\n"
                response += f"   Total journey time: {total_str}\n\n"
            
            # Add recommendation
            if connections:
                best = connections[0]
                response += f"⏰ Recommended connection: Via {best['first_leg'][1]} with a {best['transfer_time']//60}h {best['transfer_time']%60}m transfer\n"
                response += f"   Total journey time: {best['total_duration']//60}h {best['total_duration']%60}m\n"
            
            return response
            
        except Exception as e:
            logger.error(f"Error finding connecting schedule: {str(e)}")
            return f"Error finding connecting schedule: {str(e)}"
    
    def query(self, input_text: str, session_id: str = 'default') -> str:
        """
        Process user queries with conversational context.
        
        Args:
            input_text: User's input query
            session_id: Unique identifier for the chat session
            
        Returns:
            Agent's response
        """
        logger.info(f"Received schedule query: '{input_text}' for session_id: {session_id}")
        
        # Initialize conversation history if it doesn't exist
        if session_id not in self.conversations:
            logger.info(f"Initializing new chat history for session: {session_id}")
            self.conversations[session_id] = []
        
        # Get conversation history
        chat_history = self.conversations[session_id]
        logger.info(f"Current history length: {len(chat_history)}")
        
        # Check if this is a direct schedule query
        # Example: "earliest ferry from Piraeus to Mykonos"
        schedule_pattern = r"(?:find |show |what is the |when is the |)(?P<preference>earliest|latest|fastest|shortest|best|optimal)(?:ferry | schedule | route | connection |)(?:from |between |)(?P<origin>[A-Za-z\s\(\)]+)(?:to | and |)(?P<destination>[A-Za-z\s\(\)]+)(?:\s+on\s+(?P<date>\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4}))?(?:\?|\.)*$"
        schedule_match = re.match(schedule_pattern, input_text, re.IGNORECASE)
        
        if schedule_match:
            # This is a direct schedule query
            preference = schedule_match.group('preference').lower()
            origin = schedule_match.group('origin').strip()
            destination = schedule_match.group('destination').strip()
            date_str = schedule_match.group('date')
            
            # Map preference terms to our standardized options
            preference_map = {
                'earliest': 'earliest',
                'latest': 'latest',
                'fastest': 'shortest',
                'shortest': 'shortest',
                'best': 'earliest',  # Default to earliest for "best"
                'optimal': 'earliest'  # Default to earliest for "optimal"
            }
            
            std_preference = preference_map.get(preference, 'earliest')
            
            logger.info(f"Detected schedule query: {preference} from {origin} to {destination}, date: {date_str}")
            
            # Standardize date format if provided
            std_date = None
            if date_str:
                try:
                    # Try various date formats
                    if '-' in date_str:  # YYYY-MM-DD
                        std_date = date_str
                    elif '/' in date_str:  # MM/DD/YYYY
                        m, d, y = map(int, date_str.split('/'))
                        std_date = f"{y:04d}-{m:02d}-{d:02d}"
                    else:  # Month Day Year
                        parts = date_str.split()
                        month_names = ["january", "february", "march", "april", "may", "june", 
                                    "july", "august", "september", "october", "november", "december"]
                        month = month_names.index(parts[1].lower()) + 1
                        day = int(parts[0])
                        year = int(parts[2])
                        std_date = f"{year:04d}-{month:02d}-{day:02d}"
                except Exception as e:
                    logger.warning(f"Could not parse date '{date_str}': {str(e)}")
            
            # Use the specific method for this type of query
            result = self.find_optimal_schedule(origin, destination, std_date, std_preference)
            
            # Update chat history
            chat_history.append(HumanMessage(content=input_text))
            chat_history.append(AIMessage(content=result))
            
            return result
        
        # Check if this is a direct connecting routes query
        # Example: "connecting routes from Athens to Santorini"
        connecting_pattern = r"(?:find |show |what are the |)(?:connecting|connection|indirect)(?:ferry | routes | options |)(?:from |between |)(?P<origin>[A-Za-z\s\(\)]+)(?:to | and |)(?P<destination>[A-Za-z\s\(\)]+)(?:\s+on\s+(?P<date>\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4}))?(?:\?|\.)*$"
        connecting_match = re.match(connecting_pattern, input_text, re.IGNORECASE)
        
        if connecting_match:
            # This is a direct connecting routes query
            origin = connecting_match.group('origin').strip()
            destination = connecting_match.group('destination').strip()
            date_str = connecting_match.group('date')
            
            logger.info(f"Detected connecting routes query from {origin} to {destination}, date: {date_str}")
            
            # Standardize date format if provided
            std_date = None
            if date_str:
                try:
                    # Try various date formats
                    if '-' in date_str:  # YYYY-MM-DD
                        std_date = date_str
                    elif '/' in date_str:  # MM/DD/YYYY
                        m, d, y = map(int, date_str.split('/'))
                        std_date = f"{y:04d}-{m:02d}-{d:02d}"
                    else:  # Month Day Year
                        parts = date_str.split()
                        month_names = ["january", "february", "march", "april", "may", "june", 
                                    "july", "august", "september", "october", "november", "december"]
                        month = month_names.index(parts[1].lower()) + 1
                        day = int(parts[0])
                        year = int(parts[2])
                        std_date = f"{year:04d}-{month:02d}-{day:02d}"
                except Exception as e:
                    logger.warning(f"Could not parse date '{date_str}': {str(e)}")
            
            # Use the specific method for this type of query
            result = self.find_connecting_schedule(origin, destination, std_date)
            
            # Update chat history
            chat_history.append(HumanMessage(content=input_text))
            chat_history.append(AIMessage(content=result))
            
            return result
        
        # For any other type of query, use the regular agent flow
        logger.info("Invoking schedule agent executor")
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
        
        logger.info("Schedule agent response generated successfully")
        return result["output"]


# For testing
if __name__ == "__main__":
    schedule_agent = ScheduleAgent()
    print(schedule_agent.find_optimal_schedule("Piraeus", "Mykonos", preference="earliest"))
    print(schedule_agent.find_connecting_schedule("Athens", "Santorini"))