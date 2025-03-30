import os
import logging
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
            max_tokens=None,
            timeout=None,
            max_retries=2,
            google_api_key=self.api_key,
            # Don't use deprecated parameter
            # convert_system_message_to_human=True
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
            tools=[self.db_query_tool, self.port_info_tool],
            prompt=self.prompt
        )

        # Create the agent executor to handle queries
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=[self.db_query_tool, self.port_info_tool],
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
        # Check for empty input and return a helpful message
        if not input_text or input_text.strip() == "":
            return "I'm here to help with ferry information. Please ask me a question about Greek ferry routes, schedules, or prices."
            
        # Initialize chat history for the session if it doesn't exist
        if session_id not in self.chat_histories:
            self.chat_histories[session_id] = []

        session_history = self.chat_histories[session_id]

        try:
            # Invoke the agent executor with the input and chat history
            result = self.agent_executor.invoke({
                "input": input_text,
                "chat_history": session_history
            })

            # Update the chat history with the user's input and agent's response
            session_history.append(HumanMessage(content=input_text))
            session_history.append(AIMessage(content=result['output']))

            logger.info("Agent response generated successfully")
            return result['output']
            
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return "I'm sorry, I encountered an error while processing your request. Please try asking your question in a different way or try another query about ferry routes or schedules."

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