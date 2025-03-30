import os
import sqlite3
from typing import Dict, List, Union
from dotenv import load_dotenv  # Import dotenv to load environment variables

# Import necessary modules from LangChain and other libraries
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import Tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from prompt import system_prompt  # Import the system prompt from a separate file

# Load environment variables from the .env file
load_dotenv()

class DatabaseAgent:
    """
    A chatbot agent that interacts with SQLite databases and processes user queries
    using a language model (Google Gemini).
    """

    def __init__(self, db_path: str = None, historical_db_path: str = None, model_name: str = None):
        """
        Initialize the DatabaseAgent with a specified database and LLM.

        :param db_path: Path to the main SQLite database
        :param historical_db_path: Path to the historical SQLite database
        :param model_name: Google Gemini model to use
        """
        # Load database paths and model name from environment variables or use defaults
        self.db_path = os.getenv("DB_PATH", db_path)  # Main database path
        self.historical_db_path = os.getenv("HISTORICAL_DB_PATH", historical_db_path)  # Historical database path
        model_name = os.getenv("MODEL_NAME", model_name)
        api_key = os.getenv("API_KEY")  # API key for the language model

        # Raise an error if the API key is not set
        if not api_key:
            raise ValueError("API_KEY is not set in the environment variables.")

        # Initialize chat histories for each session
        self.chat_histories: Dict[str, List[Union[HumanMessage, AIMessage, SystemMessage]]] = {}

        # Initialize the language model
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.1, api_key=api_key)

        # Load the system prompt
        self.system_prompt = system_prompt

        # Define separate tools for main and historical databases
        self.main_db_tool = Tool(
            name="main_db_query",
            func=lambda q: self.run_sql_query(q, use_historical_db=False),
            description="Execute SQL queries on the main GTFS database for current schedules and prices."
        )

        self.historical_db_tool = Tool(
            name="historical_db_query",
            func=lambda q: self.run_sql_query(q, use_historical_db=True),
            description="Execute SQL queries on the historical database for past schedules and seasonal patterns."
        )

        # Define the prompt template for the agent
        self.prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=(self.system_prompt)),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

        # Create the agent using the language model and tools
        self.agent = create_tool_calling_agent(
            llm=self.llm,
            tools=[self.main_db_tool, self.historical_db_tool],
            prompt=self.prompt
        )

        # Create the agent executor to handle queries
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=[self.main_db_tool, self.historical_db_tool]
        )

    def run_sql_query(self, query: str, use_historical_db: bool = False) -> str:
        """
        Execute an SQL query against the appropriate database.
        """
        db_path = self.historical_db_path if use_historical_db else self.db_path
        db_type = 'historical' if use_historical_db else 'main'
        
        if not db_path:
            return f"Database path not set for {db_type} database"
        
        if not os.path.exists(db_path):
            return f"Database file not found: {db_path}"
        
        conn = None
        try:
            print(f"Executing query on {db_type} database: {query}")
            
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row  # Enable row factory for named columns
            cursor = conn.cursor()
            
            cursor.execute(query)
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            
            if not rows:
                return f"No results found in {db_type} database."
            
            # Format results as a table-like string
            result_str = "\n".join([
                "| " + " | ".join(str(value) for value in row) + " |"
                for row in [columns] + [dict(row).values() for row in rows]
            ])
            
            print(f"Result from {db_type} database: {result_str}")
            return result_str
            
        except sqlite3.Error as e:
            return f"Database error in {db_type} database: {e}"
        except Exception as e:
            return f"Unexpected error executing query on {db_type} database: {e}"
        finally:
            if conn:
                conn.close()

    def query(self, input_text: str, session_id: str = 'default') -> str:
        """
        Main method to process user queries with conversational context.

        :param input_text: User's input query
        :param session_id: Unique identifier for the chat session
        :return: Agent's response
        """
        # Initialize chat history for the session if it doesn't exist
        if session_id not in self.chat_histories:
            self.chat_histories[session_id] = []

        session_history = self.chat_histories[session_id]

        # Invoke the agent executor with the input and chat history
        result = self.agent_executor.invoke({
            "input": input_text,
            "chat_history": session_history
        })

        # Update the chat history with the user's input and agent's response
        session_history.append(HumanMessage(content=input_text))
        session_history.append(AIMessage(content=result['output']))

        print("Agent response:", result['output'])
        return result['output']

    def get_db_context(self):
        """
        Connects to the SQLite database specified by db_path and retrieves
        all table names along with their column names.

        :return: A dictionary where keys are table names and values are lists of column names.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        db_context = {}
        try:
            # Retrieve all table names in the database
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()

            for table in tables:
                table_name = table[0]
                if table_name == "sqlite_sequence":  # Skip internal SQLite table
                    continue

                # Retrieve column names for each table
                cursor.execute(f"PRAGMA table_info({table_name});")
                columns = cursor.fetchall()
                column_names = [column[1] for column in columns]

                db_context[table_name] = column_names

        except sqlite3.Error as e:
            print(f"An error occurred: {e}")
        finally:
            conn.close()

        # Convert the database context to a string for display
        db_context_str = str(db_context)
        print("db_context : ", db_context_str)

        return db_context_str


def main():
    """
    Main function to run the chatbot agent in a loop.
    """
    agent = DatabaseAgent()  # Initialize the DatabaseAgent

    while True:
        # Get user input
        user_input = input("User: ")
        if user_input.lower() == "exit":  # Exit the loop if the user types "exit"
            break
        # Process the user input and print the agent's response
        print("Agent:", agent.query(user_input))


if __name__ == "__main__":
    main()  # Run the main function