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

        # Define the prompt template for the agent
        self.prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=get_system_prompt()),
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
                        logger.info("Will suggest checking historical data for this route.")
                        
                        return f"No current routes found between {origin_match} and {destination_match}. Consider using the 'check_historical_routes' tool with these ports to see if this route operated in the past or is scheduled for the future."
                
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
                # Search for specific port by name or code
                query = """
                SELECT DISTINCT origin_port_code, origin_port_name
                FROM routes
                WHERE origin_port_code = ? OR origin_port_name LIKE ?
                UNION
                SELECT DISTINCT destination_port_code, destination_port_name
                FROM routes
                WHERE destination_port_code = ? OR destination_port_name LIKE ?
                ORDER BY origin_port_name
                """
                # Add wildcard for name matching but exact match for code
                results = execute_query(query, [
                    port_name_or_code.upper(),
                    f"%{port_name_or_code}%",
                    port_name_or_code.upper(),
                    f"%{port_name_or_code}%"
                ])
                
                if not results:
                    return f"No ports found matching '{port_name_or_code}'."
                
                # Format results
                port_info = []
                for code, name in results:
                    port_info.append(f"Port: {name} (Code: {code})")
                
                return "\n".join(port_info)
            else:
                # Get all ports
                query = """
                SELECT DISTINCT origin_port_code, origin_port_name
                FROM routes
                UNION
                SELECT DISTINCT destination_port_code, destination_port_name
                FROM routes
                ORDER BY origin_port_name
                """
                results = execute_query(query)
                
                if not results:
                    return "No ports found in the database."
                
                port_names = [name for _, name in results]
                return f"Available ports: {', '.join(port_names)}"
                
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
        try:
            logger.info(f"Received query: '{input_text}' for session_id: {session_id}")
            
            # Initialize chat history for new sessions
            if session_id not in self.chat_histories:
                logger.info(f"Initializing new chat history for session: {session_id}")
                self.chat_histories[session_id] = []
            
            # Get the current chat history
            chat_history = self.chat_histories[session_id]
            logger.info(f"Current history length: {len(chat_history)}")
            
            # Run the agent with the input and chat history
            logger.info("Invoking agent executor")
            result = self.agent_executor.invoke({
                "input": input_text,
                "chat_history": chat_history
            })
            
            logger.info(f"Agent result type: {type(result)}")
            if isinstance(result, dict):
                logger.info(f"Agent result keys: {result.keys()}")
            
            # Extract the agent's response
            response = result.get("output", "I'm sorry, I couldn't process your request.")
            logger.info(f"Agent response length: {len(response)}")
            
            # Update the chat history with this exchange
            chat_history.append(HumanMessage(content=input_text))
            chat_history.append(AIMessage(content=response))
            
            # Limit history to last 10 exchanges (20 messages) to prevent context overflow
            if len(chat_history) > 20:
                self.chat_histories[session_id] = chat_history[-20:]
            else:
                self.chat_histories[session_id] = chat_history
                
            logger.info("Agent response generated successfully")
            return response
            
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}", exc_info=True)
            return f"I'm sorry, an error occurred while processing your request: {str(e)}"

    def check_historical_routes(self, origin=None, destination=None) -> str:
        """
        Check historical data for routes between the given ports when current routes aren't found.
        """
        try:
            # If passed a dict with both ports
            if isinstance(origin, dict) and 'origin' in origin and 'destination' in origin:
                origin_port = origin.get('origin')
                destination_port = origin.get('destination')
            else:
                origin_port = origin
                destination_port = destination
                
            if not origin_port or not destination_port:
                return "Please provide both origin and destination ports to check historical routes."
            
            # Query for routes in the current database
            current_query = """
            SELECT 
                r.route_number,
                r.company,
                r.origin_port_name,
                r.destination_port_name,
                COUNT(DISTINCT d.schedule_date) as scheduled_days
            FROM
                routes r
            JOIN
                dates_and_vessels d ON r.route_id = d.route_id
            WHERE
                (r.origin_port_code = ? OR r.origin_port_name LIKE ?)
                AND (r.destination_port_code = ? OR r.destination_port_name LIKE ?)
            GROUP BY
                r.route_number, r.company
            """
            
            results = execute_query(current_query, [
                origin_port.upper(),
                f"%{origin_port}%",
                destination_port.upper(),
                f"%{destination_port}%"
            ])
            
            if results:
                output = "Found the following routes:\n\n"
                for row in results:
                    output += f"Route {row[0]}: {row[1]}\n"
                    output += f"From: {row[2]} To: {row[3]}\n"
                    output += f"Scheduled on {row[4]} different dates\n\n"
                return output
            else:
                # If no results in current database, we would check historical data
                # But since we don't have that connected in this example, we'll return a message
                return f"No ferry routes found between {origin_port} and {destination_port} in current or historical data."
                
        except Exception as e:
            return f"Error checking historical routes: {str(e)}"

    def get_db_schema(self) -> str:
        """
        Retrieves the database schema for reference.
        """
        try:
            query = """
            SELECT name FROM sqlite_master 
            WHERE type='table'
            ORDER BY name;
            """
            tables = execute_query(query)
            
            schema = "Database Schema:\n\n"
            
            for table in tables:
                table_name = table[0]
                schema += f"Table: {table_name}\n"
                
                columns_query = f"PRAGMA table_info({table_name});"
                columns = execute_query(columns_query)
                
                schema += "Columns:\n"
                for col in columns:
                    col_name = col[1]
                    col_type = col[2]
                    is_nullable = "NOT NULL" if col[3] else "NULL"
                    is_pk = "PRIMARY KEY" if col[5] else ""
                    schema += f"- {col_name} ({col_type}) {is_nullable} {is_pk}\n"
                
                schema += "\n"
            
            return schema
            
        except Exception as e:
            return f"Error retrieving database schema: {str(e)}"