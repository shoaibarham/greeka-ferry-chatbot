import os
import logging
import sqlite3
from typing import Dict, List, Any, Optional, Union
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import Tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from prompts.system_prompt import get_system_prompt
from config import GEMINI_API_KEY, MODEL_NAME, AGENT_TEMPERATURE
from db import execute_query

logger = logging.getLogger(__name__)

class FerryAgent:
    """
    An agent that handles ferry information queries using a language model (Google Gemini).
    """

    def __init__(self):
        """
        Initialize the FerryAgent with a specified LLM.
        """
        self.api_key = GEMINI_API_KEY
        
        # Raise an error if the API key is not set
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set in the environment variables.")

        # Initialize chat histories for each session
        self.chat_histories: Dict[str, List[Union[HumanMessage, AIMessage, SystemMessage]]] = {}

        # Initialize the language model
        self.llm = ChatGoogleGenerativeAI(
            model=MODEL_NAME,
            temperature=AGENT_TEMPERATURE,
            max_output_tokens=2048,  # Set a specific max token limit
            timeout=60,  # Set a specific timeout
            max_retries=3,
            google_api_key=self.api_key
        )

        # Define the main database query tool
        self.db_query_tool = Tool(
            name="run_ferry_query",
            func=self.run_ferry_query,
            description="Execute SQL queries on the ferry database to retrieve information about routes, schedules, and prices."
        )

        # Define tools for getting port information
        self.port_info_tool = Tool(
            name="get_port_information",
            func=self.get_port_information,
            description="Get information about ports including codes and names."
        )
        
        # Define tool for checking historical data
        self.historical_data_tool = Tool(
            name="check_historical_routes",
            func=self.check_historical_routes,
            description="Check if a route was available in historical data when it's not found in current schedules."
        )

        # Define the prompt template for the agent with enhanced instructions
        system_prompt_content = get_system_prompt()
        # Add special emphasis on checking historical data for routes
        special_instruction = "\n\nCRITICAL INSTRUCTION: When a user asks about routes and no current routes are found, you MUST ALWAYS use the check_historical_routes tool before giving a negative response. Never skip this step!"
        
        self.prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=system_prompt_content + special_instruction),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

        # Create the agent using the language model and tools
        self.agent = create_tool_calling_agent(
            llm=self.llm,
            tools=[self.db_query_tool, self.port_info_tool, self.historical_data_tool],
            prompt=self.prompt
        )

        # Create the agent executor to handle queries
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=[self.db_query_tool, self.port_info_tool, self.historical_data_tool],
            verbose=True
        )

    def run_ferry_query(self, query: str) -> str:
        """
        Execute an SQL query against the ferry database.
        """
        try:
            logging.info(f"Executing query: {query}")
            
            # Block potentially dangerous SQL operations
            forbidden_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'TRUNCATE']
            if any(keyword in query.upper() for keyword in forbidden_keywords):
                return "Error: Potentially dangerous SQL query detected."
            
            # Execute the query
            results = execute_query(query)
            
            if not results:
                # Try to detect if this is a route search query
                if "SELECT" in query.upper() and "FROM routes" in query.upper() and "origin_port" in query.lower() and "destination_port" in query.lower():
                    logger.info("Route search query with no results detected. Should check historical data.")
                    
                    # Extract origin and destination from query (basic extraction)
                    origin_match = None
                    destination_match = None
                    
                    # Check for LIKE conditions with port names or codes
                    import re
                    origin_pattern = r"(origin_port_name|origin_port_code)[\s]+LIKE[\s]+['\"]%([^'\"]+)%['\"]"
                    destination_pattern = r"(destination_port_name|destination_port_code)[\s]+LIKE[\s]+['\"]%([^'\"]+)%['\"]"
                    
                    origin_matches = re.findall(origin_pattern, query, re.IGNORECASE)
                    destination_matches = re.findall(destination_pattern, query, re.IGNORECASE)
                    
                    if origin_matches and destination_matches:
                        origin_match = origin_matches[0][1]
                        destination_match = destination_matches[0][1]
                        
                        logger.info(f"Extracted origin: {origin_match}, destination: {destination_match}")
                        logger.info("Automatically checking historical data for this route.")
                        
                        # Instead of suggesting to use the tool, directly call the check_historical_routes method
                        historical_data = self.check_historical_routes(origin_match, destination_match)
                        
                        if "No historical routes found" in historical_data:
                            return f"I don't see any direct ferry routes from {origin_match} to {destination_match} at the moment. For travel between these destinations, you might want to consider a route via a major Greek hub like Piraeus or Mykonos."
                        else:
                            # Extract the relevant information without mentioning "historical data"
                            import re
                            match = re.search(r"This route (operated in the past|is scheduled to operate|operates seasonally) .*?\.", historical_data)
                            if match:
                                date_info = match.group(0)
                                return f"I don't see any direct ferry routes from {origin_match} to {destination_match} at the moment. {date_info}"
                            else:
                                return f"I don't see any direct ferry routes from {origin_match} to {destination_match} at the moment."
                
                return "No results found for the given query."
            
            # Format the results as a readable string
            if results and len(results) > 0:
                if isinstance(results[0], tuple):
                    # If results are tuples (actual database rows)
                    result_lines = [str(row) for row in results]
                    return "\n".join(result_lines)
                else:
                    # If results are already strings
                    return "\n".join(results)
            else:
                return "No results found."
            
        except Exception as e:
            return f"Error executing query: {str(e)}"

    def get_port_information(self, port_name_or_code: str = None) -> str:
        """
        Get information about ports. If a specific port is not provided,
        return all ports. Otherwise, search for the specified port.
        """
        try:
            if port_name_or_code:
                # Search for a specific port
                query = """
                SELECT DISTINCT origin_port_code as code, origin_port_name as name FROM routes
                WHERE LOWER(origin_port_code) = LOWER(?) OR LOWER(origin_port_name) LIKE LOWER(?)
                UNION
                SELECT DISTINCT destination_port_code as code, destination_port_name as name FROM routes
                WHERE LOWER(destination_port_code) = LOWER(?) OR LOWER(destination_port_name) LIKE LOWER(?)
                ORDER BY name
                """
                search_pattern = f"%{port_name_or_code}%"
                results = execute_query(query, 
                                       (port_name_or_code, search_pattern, port_name_or_code, search_pattern))
            else:
                # Get all ports
                query = """
                SELECT DISTINCT origin_port_code as code, origin_port_name as name FROM routes
                UNION
                SELECT DISTINCT destination_port_code as code, destination_port_name as name FROM routes
                ORDER BY name
                """
                results = execute_query(query)
            
            if not results:
                return "No ports found matching the criteria."
            
            # Format the results
            ports_info = []
            for row in results:
                ports_info.append(f"{row[0]}: {row[1]}")
            
            return "\n".join(ports_info)
            
        except Exception as e:
            return f"Error retrieving port information: {str(e)}"

    def query(self, input_text: str, session_id: str = 'default') -> str:
        """
        Main method to process user queries with conversational context.

        Args:
            input_text: User's input query
            session_id: Unique identifier for the chat session
            
        Returns:
            Agent's response
        """
        logger.info(f"Received query: '{input_text}' for session_id: {session_id}")
        
        # Check for empty input and return a helpful message
        if not input_text or input_text.strip() == "":
            logger.info("Empty query received, returning default message")
            return "I'm here to help with ferry information. Please ask me a question about Greek ferry routes, schedules, or prices."
            
        # Initialize chat history for the session if it doesn't exist
        if session_id not in self.chat_histories:
            logger.info(f"Initializing new chat history for session: {session_id}")
            self.chat_histories[session_id] = []

        session_history = self.chat_histories[session_id]
        logger.info(f"Current history length: {len(session_history)}")

        try:
            logger.info("Invoking agent executor")
            # Invoke the agent executor with the input and chat history
            result = self.agent_executor.invoke({
                "input": input_text,
                "chat_history": session_history
            })
            
            logger.info(f"Agent result type: {type(result)}")
            logger.info(f"Agent result keys: {result.keys() if isinstance(result, dict) else 'Not a dict'}")
            
            if isinstance(result, dict) and 'output' in result:
                output = result['output']
                logger.info(f"Agent response length: {len(output) if output else 0}")
                
                # Update the chat history with the user's input and agent's response
                session_history.append(HumanMessage(content=input_text))
                session_history.append(AIMessage(content=output))
                
                logger.info("Agent response generated successfully")
                return output
            else:
                logger.error(f"Invalid response format: {result}")
                return "The system responded in an unexpected format. Please try again with a different question."
            
        except Exception as e:
            import traceback
            logger.error(f"Error processing query: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return "I'm sorry, I encountered an error while processing your request. Please try asking your question in a different way or try another query about ferry routes or schedules."

    def check_historical_routes(self, param1=None, param2=None) -> str:
        """
        Check historical data for routes between the given ports when current routes aren't found.
        
        Args:
            param1: Either the origin port name or a dictionary containing both ports
            param2: The destination port name if param1 is a string
            
        Returns:
            Information about historical routes if found, or a message indicating no historical data
        """
        origin_port = None
        destination_port = None
        
        # Enable detailed logging for parameter inspection
        logger.info(f"check_historical_routes received: param1={param1}, param2={param2}")
        
        # Case 1: Simple string parameters
        if isinstance(param1, str) and isinstance(param2, str) and param2 is not None:
            # This is the simplest case - two string parameters
            origin_port = param1
            destination_port = param2
            logger.info(f"Using direct string parameters: origin={origin_port}, destination={destination_port}")
            
        # Case 2: Dictionary parameter
        elif isinstance(param1, dict):
            logger.info(f"Processing dictionary input: {param1}")
            
            # Try to extract values based on common key patterns
            if 'origin_port' in param1 and 'destination_port' in param1:
                origin_port = param1['origin_port']
                destination_port = param1['destination_port']
                logger.info(f"Extracted from standard keys: origin={origin_port}, destination={destination_port}")
            
            elif 'origin' in param1 and 'destination' in param1:
                origin_port = param1['origin']
                destination_port = param1['destination']
                logger.info(f"Extracted from short keys: origin={origin_port}, destination={destination_port}")
                
            # If it's just a flat dictionary with exactly two values, use those
            elif len(param1) == 2:
                keys = list(param1.keys())
                origin_port = param1[keys[0]]
                destination_port = param1[keys[1]]
                logger.info(f"Extracted from generic keys: origin={origin_port}, destination={destination_port}")
                
            # Special case: Sometimes LangChain sends a dict with just one key
            elif len(param1) == 1 and isinstance(list(param1.values())[0], dict):
                inner_dict = list(param1.values())[0]
                logger.info(f"Found nested dictionary: {inner_dict}")
                
                if 'origin_port' in inner_dict and 'destination_port' in inner_dict:
                    origin_port = inner_dict['origin_port']
                    destination_port = inner_dict['destination_port']
                    logger.info(f"Extracted from nested dict: origin={origin_port}, destination={destination_port}")
                elif len(inner_dict) >= 2:
                    inner_keys = list(inner_dict.keys())
                    origin_port = inner_dict[inner_keys[0]]
                    destination_port = inner_dict[inner_keys[1]]
                    logger.info(f"Extracted from nested generic keys: origin={origin_port}, destination={destination_port}")
        
        # Case 3: String parameter that might be a dictionary representation
        elif isinstance(param1, str):
            # First, try treating it as a standard string parameter
            if param2 is not None and isinstance(param2, str):
                origin_port = param1
                destination_port = param2
                logger.info(f"Using string parameters: origin={origin_port}, destination={destination_port}")
            # Next, check if it's a string representation of a dictionary
            elif '{' in param1 and '}' in param1:
                logger.info(f"Processing potential dictionary string: {param1}")
                
                try:
                    # Try to convert Python string repr to proper JSON format
                    import json
                    import re
                    
                    # Replace single quotes with double quotes for JSON parsing
                    json_string = re.sub(r"'([^']*)':", r'"\1":', param1)
                    json_string = re.sub(r":\s*'([^']*)'", r': "\1"', json_string)
                    
                    logger.info(f"Converted to JSON format: {json_string}")
                    json_dict = json.loads(json_string)
                    
                    # Extract values from the parsed dictionary
                    if 'origin_port' in json_dict and 'destination_port' in json_dict:
                        origin_port = json_dict['origin_port']
                        destination_port = json_dict['destination_port']
                        logger.info(f"Extracted from converted JSON: origin={origin_port}, destination={destination_port}")
                    elif 'origin' in json_dict and 'destination' in json_dict:
                        origin_port = json_dict['origin']
                        destination_port = json_dict['destination']
                        logger.info(f"Extracted from converted JSON: origin={origin_port}, destination={destination_port}")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse as JSON: {str(e)}")
                except Exception as e:
                    logger.error(f"Error processing JSON string: {str(e)}")
                
        # Case 3: First parameter is a string containing a key-value format (LangChain workaround)
        elif isinstance(param1, str) and param1.find(':') > 0:
            logger.info(f"Processing potential key-value string: {param1}")
            
            # Try format like "origin_port:Brindisi destination_port:Corfu"
            if 'origin_port' in param1 and 'destination_port' in param1:
                try:
                    # Split on 'destination_port:'
                    parts = param1.split('destination_port:')
                    origin_part = parts[0].strip()
                    destination_part = parts[1].strip()
                    
                    # Extract origin value by removing 'origin_port:'
                    origin_port = origin_part.replace('origin_port:', '').strip()
                    # Remove any trailing comma or whitespace from destination
                    destination_port = destination_part.strip().strip(',')
                    
                    # Handle potential comma delimiter
                    if origin_port.endswith(','):
                        origin_port = origin_port[:-1].strip()
                        
                    logger.info(f"Extracted from key-value string: origin={origin_port}, destination={destination_port}")
                except Exception as e:
                    logger.error(f"Error parsing key-value string: {str(e)}")
                    
            # Try to handle any kind of colon-separated key-value format
            if not origin_port or not destination_port:
                try:
                    # Split the string by spaces and look for key:value pairs
                    parts = param1.split(' ')
                    port_dict = {}
                    
                    for part in parts:
                        if ':' in part:
                            key_val = part.split(':')
                            if len(key_val) == 2:
                                key, val = key_val
                                port_dict[key.strip()] = val.strip().strip(',')
                    
                    logger.info(f"Parsed key-value pairs: {port_dict}")
                    
                    # Look for origin/destination keys in various formats
                    for key in port_dict:
                        if 'origin' in key.lower():
                            origin_port = port_dict[key]
                        elif 'destination' in key.lower() or 'dest' in key.lower():
                            destination_port = port_dict[key]
                            
                    logger.info(f"Extracted from key-value parsing: origin={origin_port}, destination={destination_port}")
                except Exception as e:
                    logger.error(f"Error in advanced key-value parsing: {str(e)}")
        
        # Case 4: First parameter is a string and second parameter is a string (direct invocation)
        elif isinstance(param1, str) and isinstance(param2, str):
            origin_port = param1
            destination_port = param2
            logger.info(f"Using direct string parameters: origin={origin_port}, destination={destination_port}")
            
        # Case 5: Special case - direct string parameters for simple route checking 
        elif isinstance(param1, str) and not param2:
            logger.info(f"Processing as a direct route query: {param1}")
            
            # Handle cases like "Brindisi to Corfu"
            if ' to ' in param1.lower():
                parts = param1.lower().split(' to ')
                if len(parts) == 2:
                    origin_port = parts[0].strip()
                    destination_port = parts[1].strip()
                    logger.info(f"Extracted from 'X to Y' format: origin={origin_port}, destination={destination_port}")
                    
            # Handle cases like "from Brindisi to Corfu"
            elif 'from ' in param1.lower() and ' to ' in param1.lower():
                from_idx = param1.lower().find('from ')
                to_idx = param1.lower().find(' to ')
                if from_idx >= 0 and to_idx > from_idx:
                    origin_port = param1[from_idx + 5:to_idx].strip()
                    destination_port = param1[to_idx + 4:].strip()
                    logger.info(f"Extracted from 'from X to Y' format: origin={origin_port}, destination={destination_port}")
        
        # Final validation - ensure we have both values
        if not origin_port or not destination_port:
            error_message = f"Error: Could not extract origin and destination ports from parameters: param1={param1}, param2={param2}"
            logger.error(error_message)
            # Try to be more helpful in the response by including debugging info
            if isinstance(param1, dict):
                error_message += f"\nReceived dictionary with keys: {list(param1.keys())}"
            return error_message
        try:
            logger.info(f"Checking historical routes from {origin_port} to {destination_port}")
            
            # Connect to the historical database
            db_path = 'previous_db.db'
            if not os.path.exists(db_path):
                return "Historical database does not exist. Unable to check past routes."
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Clean the input parameters to improve matching
            origin_port = origin_port.strip().lower()
            destination_port = destination_port.strip().lower()
            
            # Log the cleaned parameters
            logger.info(f"Cleaned parameters - origin: '{origin_port}', destination: '{destination_port}'")
            
            # Search in the historical_date_ranges table with case-insensitive comparison
            query = """
            SELECT 
                origin_name, destination_name, 
                MIN(start_date) AS earliest_start,
                MAX(end_date) AS latest_end, 
                MIN(appear_date) AS first_appeared,
                COUNT(*) AS data_points
            FROM historical_date_ranges
            WHERE 
                (LOWER(origin_code) = LOWER(?) OR LOWER(origin_name) LIKE LOWER(?)) AND
                (LOWER(destination_code) = LOWER(?) OR LOWER(destination_name) LIKE LOWER(?))
            GROUP BY origin_name, destination_name
            """
            
            # Create search patterns
            origin_pattern = f"%{origin_port}%"
            destination_pattern = f"%{destination_port}%"
            
            # Log the query parameters
            logger.info(f"Running historical search with patterns: origin='{origin_pattern}', destination='{destination_pattern}'")
            
            cursor.execute(query, (origin_port, origin_pattern, destination_port, destination_pattern))
            results = cursor.fetchall()
            
            # Log the number of results found
            logger.info(f"Found {len(results) if results else 0} results in forward direction")
            
            if not results or len(results) == 0:
                # Try the reverse direction
                logger.info(f"Trying reverse direction search")
                cursor.execute(query, (destination_port, destination_pattern, origin_port, origin_pattern))
                results = cursor.fetchall()
                
                # Log the number of results found in reverse direction
                logger.info(f"Found {len(results) if results else 0} results in reverse direction")
                
                if not results or len(results) == 0:
                    # Try a more fuzzy search by using just the first few characters
                    logger.info("Trying fuzzy search with shorter patterns")
                    
                    # Get the first 3-4 characters of each port name for a more fuzzy search
                    origin_fuzzy = origin_port[:min(4, len(origin_port))]
                    dest_fuzzy = destination_port[:min(4, len(destination_port))]
                    
                    origin_fuzzy_pattern = f"%{origin_fuzzy}%"
                    dest_fuzzy_pattern = f"%{dest_fuzzy}%"
                    
                    logger.info(f"Fuzzy patterns: origin='{origin_fuzzy_pattern}', destination='{dest_fuzzy_pattern}'")
                    
                    # Try forward direction with fuzzy patterns
                    cursor.execute(query, (origin_port, origin_fuzzy_pattern, destination_port, dest_fuzzy_pattern))
                    results = cursor.fetchall()
                    
                    logger.info(f"Found {len(results) if results else 0} results with fuzzy forward search")
                    
                    if not results or len(results) == 0:
                        # Try reverse direction with fuzzy patterns
                        cursor.execute(query, (destination_port, dest_fuzzy_pattern, origin_port, origin_fuzzy_pattern))
                        results = cursor.fetchall()
                        
                        logger.info(f"Found {len(results) if results else 0} results with fuzzy reverse search")
                        
                        if not results or len(results) == 0:
                            return f"No historical routes found between {origin_port} and {destination_port} in either direction."
            
            # Format the results
            from datetime import datetime
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            historical_info = []
            for row in results:
                origin, destination, earliest_start, latest_end, first_appeared, count = row
                
                # Log the row data
                logger.info(f"Processing row: {row}")
                
                # Format the dates to be more readable
                def format_date(date_str):
                    # Convert YYYY-MM-DD to Month DD, YYYY format
                    try:
                        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                        return date_obj.strftime("%B %d, %Y")
                    except:
                        return date_str  # Return original if parsing fails
                
                earliest_readable = format_date(earliest_start)
                latest_readable = format_date(latest_end)
                
                # Extract years and months for detailed information
                start_month = ""
                end_month = ""
                start_year = ""
                end_year = ""
                try:
                    start_date = datetime.strptime(earliest_start, "%Y-%m-%d")
                    end_date = datetime.strptime(latest_end, "%Y-%m-%d")
                    start_month = start_date.strftime("%B")
                    end_month = end_date.strftime("%B")
                    start_year = start_date.strftime("%Y")
                    end_year = end_date.strftime("%Y")
                except:
                    pass
                
                # Check if the route is entirely in the past, future, or spans the current date
                message = ""
                season = "summer" if start_month in ["June", "July", "August", "September"] else "winter"
                
                if latest_end < current_date:
                    # For past routes
                    message = f"This route operated during the {season} season from {start_month} to {end_month}. In previous years, this route ran from {start_month} {start_year} to {end_month} {end_year}."
                elif earliest_start > current_date:
                    # For future routes
                    message = f"This route is scheduled to operate from {earliest_readable} to {latest_readable}. Please check closer to the departure date for ticket availability."
                else:
                    # For current/seasonal routes
                    if start_month == end_month:
                        message = f"This route typically operates during {start_month}. In previous years, it was available in {start_month} {start_year}."
                    else:
                        message = f"This route typically operates during the {season} season from {start_month} to {end_month}. In previous years, this route ran from {start_month} {start_year} to {end_month} {end_year}."
                
                historical_info.append(message)
            
            conn.close()
            
            result = " ".join(historical_info)
            logger.info(f"Returning historical data result with {len(historical_info)} entries")
            return result
            
        except Exception as e:
            logger.error(f"Error checking historical routes: {str(e)}")
            return f"Error searching historical routes: {str(e)}"

    def get_db_schema(self) -> str:
        """
        Retrieves the database schema for reference.
        """
        try:
            # For SQLite, we need to use a different approach to get table information
            tables_query = """
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
            tables = execute_query(tables_query)
            
            schema_info = []
            for table in tables:
                table_name = table[0]
                # Get columns for the table using PRAGMA
                columns_query = f"PRAGMA table_info({table_name})"
                columns = execute_query(columns_query)
                
                column_info = [f"  - {col[1]} ({col[2]})" for col in columns]  # col[1] is name, col[2] is type
                schema_info.append(f"Table: {table_name}")
                schema_info.extend(column_info)
                schema_info.append("")  # Add blank line between tables
            
            return "\n".join(schema_info)
        except Exception as e:
            return f"Error retrieving database schema: {str(e)}"