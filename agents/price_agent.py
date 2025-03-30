"""
Price Comparison Agent - Specialized agent for finding and comparing ferry ticket prices.

This agent focuses on finding the cheapest tickets and performing price analysis,
comparing accommodation prices across vessels and providing detailed price breakdowns.
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

class PriceAgent:
    """
    A specialized agent that focuses on finding and comparing ferry ticket prices.
    """
    
    def __init__(self):
        """
        Initialize the PriceAgent with specialized price comparison capabilities.
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
                "name": "run_price_query",
                "description": "Execute an SQL query against the ferry database to find ticket prices",
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
                "name": "get_cheapest_routes",
                "description": "Find the cheapest ferry routes from a specified location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "origin": {
                            "type": "string",
                            "description": "The origin port or location"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "The maximum number of results to return (default 5)"
                        }
                    },
                    "required": ["origin"]
                }
            },
            {
                "name": "compare_ticket_prices",
                "description": "Compare ticket prices between specified routes",
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
                self.run_price_query, 
                self.get_cheapest_routes, 
                self.compare_ticket_prices
            ],
            verbose=True
        )
        
        logger.info("Price Agent initialized successfully")
    
    def _get_system_prompt(self) -> str:
        """
        Returns the specialized system prompt for the price comparison agent.
        """
        return """
        You are a Price Specialist for FerriesinGreece, focusing exclusively on finding and comparing ferry ticket prices.

        MAIN RESPONSIBILITIES:
        - Find the cheapest tickets for specific routes
        - Compare prices across different vessels and companies
        - Provide detailed price breakdowns by accommodation type
        - Find the cheapest destinations from a given port

        DATABASE STRUCTURE:
        - Main DB (gtfs.db) contains the following relevant tables:
        
          1. routes: Contains route information
             Fields: route_id, company, origin_port_name, destination_port_name
          
          2. vessels_and_indicative_prices: Basic ticket prices
             Fields: route_id, vessel, indicative_price (in cents)
          
          3. vessels_and_accommodation_prices: Detailed cabin/seat prices
             Fields: route_id, vessel, accommodation_type, price (in cents)

        IMPORTANT PRICE INFORMATION:
        - All prices in the database are stored in CENTS (not euros)
        - Always convert prices to euros by dividing by 100 before showing to users
        - Format all prices as €XX.XX
        - When comparing prices, always show percentages for price differences
        - For accommodation types, decode the codes for better readability:
          * DECK___DECK: Standard deck passage
          * EC___Economy: Economy numbered seat
          * ACLSS___VIP: VIP Lounge 
          * AA2___: 2-bed outside cabin
          * AB2___: 2-bed inside cabin

        RESPONSE FORMAT:
        - For cheapest routes: List in order of price, showing origin, destination, company, and price
        - For price comparisons: Create a table format showing company, vessel, accommodation types and prices
        - Always include a summary with the best value options
        
        SEARCH TIPS:
        - For Athens, check prices from Lavrio, Rafina, and Piraeus ports
        - DB values are in CAPITAL LETTERS, use case-insensitive queries (LOWER())
        - Null or zero prices should be excluded from comparisons
        """
    
    def run_price_query(self, query: str) -> str:
        """
        Execute an SQL query against the ferry database to find price information.
        
        Args:
            query: SQL query to execute
            
        Returns:
            Query results or error message
        """
        try:
            logger.info(f"Executing price query: {query}")
            conn = sqlite3.connect(MAIN_DB_PATH)
            cursor = conn.cursor()
            cursor.execute(query)
            results = cursor.fetchall()
            conn.close()
            
            if not results:
                return "No price results found for the given query."
            
            # Return the results as a string
            return str(results)
        except Exception as e:
            logger.error(f"Error executing price query: {str(e)}")
            return f"Error executing price query: {str(e)}"
    
    def get_cheapest_routes(self, origin: str, limit: int = 5) -> str:
        """
        Find the cheapest ferry routes from a specified location.
        
        Args:
            origin: The origin port or location
            limit: Maximum number of results to return
            
        Returns:
            List of cheapest routes with prices
        """
        logger.info(f"Finding cheapest routes from {origin}, limit {limit}")
        
        # Check if the origin is Athens, which requires checking multiple ports
        is_athens = origin.lower() in ['athens', 'athina', 'αθήνα', 'αθηνα']
        
        try:
            conn = sqlite3.connect(MAIN_DB_PATH)
            cursor = conn.cursor()
            
            if is_athens:
                # For Athens, check prices from all three major ports
                logger.info("Searching Athens ports (Piraeus, Rafina, Lavrio)")
                query = """
                SELECT 
                    r.origin_port_name, 
                    r.destination_port_name, 
                    r.company, 
                    v.indicative_price/100.0 as price_euros,
                    r.route_id
                FROM 
                    routes r
                JOIN 
                    vessels_and_indicative_prices v ON r.route_id = v.route_id
                WHERE 
                    LOWER(r.origin_port_name) IN ('piraeus', 'rafina', 'lavrio')
                    AND v.indicative_price > 0
                ORDER BY 
                    v.indicative_price ASC
                LIMIT ?
                """
                cursor.execute(query, (limit,))
            else:
                # For other origins, search by the specified location
                query = """
                SELECT 
                    r.origin_port_name, 
                    r.destination_port_name, 
                    r.company, 
                    v.indicative_price/100.0 as price_euros,
                    r.route_id
                FROM 
                    routes r
                JOIN 
                    vessels_and_indicative_prices v ON r.route_id = v.route_id
                WHERE 
                    LOWER(r.origin_port_name) LIKE LOWER(?)
                    AND v.indicative_price > 0
                ORDER BY 
                    v.indicative_price ASC
                LIMIT ?
                """
                cursor.execute(query, (f'%{origin}%', limit))
            
            results = cursor.fetchall()
            conn.close()
            
            if not results:
                return f"No routes found departing from {origin} with price information."
            
            # Format the results into a readable response
            response = f"The cheapest ferry routes from {origin} are:\n\n"
            
            for i, (orig, dest, company, price, _) in enumerate(results, 1):
                response += f"{i}. {orig} to {dest}\n"
                response += f"   Company: {company}\n"
                response += f"   Price: €{price:.2f}\n\n"
            
            return response
            
        except Exception as e:
            logger.error(f"Error finding cheapest routes: {str(e)}")
            return f"Error finding cheapest routes: {str(e)}"
    
    def compare_ticket_prices(self, origin: str, destination: str) -> str:
        """
        Compare ticket prices between specified routes.
        
        Args:
            origin: The origin port or location
            destination: The destination port or location
            
        Returns:
            Comparison of ticket prices for the specified route
        """
        logger.info(f"Comparing ticket prices from {origin} to {destination}")
        
        try:
            conn = sqlite3.connect(MAIN_DB_PATH)
            cursor = conn.cursor()
            
            # Get basic route information and indicative prices
            query = """
            SELECT 
                r.route_id,
                r.company, 
                r.departure_time,
                r.arrival_time,
                v.vessel,
                v.indicative_price/100.0 as basic_price
            FROM 
                routes r
            JOIN 
                vessels_and_indicative_prices v ON r.route_id = v.route_id
            WHERE 
                LOWER(r.origin_port_name) LIKE LOWER(?)
                AND LOWER(r.destination_port_name) LIKE LOWER(?)
                AND v.indicative_price > 0
            ORDER BY 
                v.indicative_price ASC
            """
            
            cursor.execute(query, (f'%{origin}%', f'%{destination}%'))
            basic_results = cursor.fetchall()
            
            if not basic_results:
                return f"No route options found from {origin} to {destination} with price information."
            
            # Format the comparison results
            response = f"Price comparison for ferry routes from {origin} to {destination}:\n\n"
            
            # Process each route option
            for route_id, company, dep_time, arr_time, vessel, basic_price in basic_results:
                response += f"Company: {company}\n"
                response += f"Vessel: {vessel.split('___')[1] if '___' in vessel else vessel}\n"
                response += f"Departure: {dep_time}, Arrival: {arr_time}\n"
                response += f"Basic ticket: €{basic_price:.2f}\n\n"
                
                # Get accommodation prices for this route
                accom_query = """
                SELECT 
                    accommodation_type,
                    price/100.0 as accom_price
                FROM 
                    vessels_and_accommodation_prices
                WHERE 
                    route_id = ?
                    AND vessel = ?
                    AND price > 0
                ORDER BY 
                    price ASC
                """
                
                cursor.execute(accom_query, (route_id, vessel))
                accom_results = cursor.fetchall()
                
                if accom_results:
                    response += "Accommodation options:\n"
                    for accom_type, price in accom_results:
                        # Clean up the accommodation type name
                        clean_type = accom_type.split('___')[1] if '___' in accom_type else accom_type
                        response += f"- {clean_type}: €{price:.2f}\n"
                    
                    response += "\n"
            
            # Add a summary with the cheapest option
            if basic_results:
                cheapest = min(basic_results, key=lambda x: x[5])
                response += f"💰 Best value option: {cheapest[1]} with basic fare at €{cheapest[5]:.2f}\n"
            
            conn.close()
            return response
            
        except Exception as e:
            logger.error(f"Error comparing ticket prices: {str(e)}")
            return f"Error comparing ticket prices: {str(e)}"
    
    def find_cheapest_destinations(self, origin: str, limit: int = 5) -> str:
        """
        Find the cheapest destinations from a given origin port.
        
        Args:
            origin: The origin port or location
            limit: Maximum number of results to return
            
        Returns:
            List of cheapest destinations with prices
        """
        return self.get_cheapest_routes(origin, limit)
    
    def find_best_value_tickets(self, origin: str, destination: str) -> str:
        """
        Find the best value tickets for a specific route.
        
        Args:
            origin: The origin port or location
            destination: The destination port or location
            
        Returns:
            Best value ticket options
        """
        return self.compare_ticket_prices(origin, destination)
    
    def query(self, input_text: str, session_id: str = 'default') -> str:
        """
        Process user queries with conversational context.
        
        Args:
            input_text: User's input query
            session_id: Unique identifier for the chat session
            
        Returns:
            Agent's response
        """
        logger.info(f"Received price query: '{input_text}' for session_id: {session_id}")
        
        # Initialize conversation history if it doesn't exist
        if session_id not in self.conversations:
            logger.info(f"Initializing new chat history for session: {session_id}")
            self.conversations[session_id] = []
        
        # Get conversation history
        chat_history = self.conversations[session_id]
        logger.info(f"Current history length: {len(chat_history)}")
        
        # Check if this is a direct "cheapest from" query
        cheapest_pattern = r"(?:what are the |find |show |list |)(?:cheapest|least expensive)(?:ferry | |)(?:routes |tickets |trips |)(?:from |departing from |starting from |)([A-Za-z\s\(\)]+)(?:\?|\.)*$"
        cheapest_match = re.match(cheapest_pattern, input_text, re.IGNORECASE)
        
        if cheapest_match:
            # This is a direct "cheapest from" query
            origin = cheapest_match.group(1).strip()
            logger.info(f"Detected cheapest routes query from: {origin}")
            
            # Use the specific method for this type of query
            result = self.get_cheapest_routes(origin)
            
            # Update chat history
            chat_history.append(HumanMessage(content=input_text))
            chat_history.append(AIMessage(content=result))
            
            return result
        
        # Check if this is a direct comparison query
        compare_pattern = r"(?:compare |show |find |)(?:the |)(?:prices|tickets|fares|costs)(?:for | |)(?:ferries |routes |)(?:from |between |)([A-Za-z\s\(\)]+)(?:to | and |)([A-Za-z\s\(\)]+)(?:\?|\.)*$"
        compare_match = re.match(compare_pattern, input_text, re.IGNORECASE)
        
        if compare_match:
            # This is a direct comparison query
            origin = compare_match.group(1).strip()
            destination = compare_match.group(2).strip()
            logger.info(f"Detected price comparison query from {origin} to {destination}")
            
            # Use the specific method for this type of query
            result = self.compare_ticket_prices(origin, destination)
            
            # Update chat history
            chat_history.append(HumanMessage(content=input_text))
            chat_history.append(AIMessage(content=result))
            
            return result
        
        # For any other type of query, use the regular agent flow
        logger.info("Invoking price agent executor")
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
        
        logger.info("Price agent response generated successfully")
        return result["output"]


# For testing
if __name__ == "__main__":
    price_agent = PriceAgent()
    print(price_agent.get_cheapest_routes("Piraeus"))
    print(price_agent.compare_ticket_prices("Piraeus", "Mykonos"))