from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from agent import DatabaseAgent
import uvicorn
from dotenv import load_dotenv
import os
import os.path

# Load environment variables from the .env file
load_dotenv()

# Retrieve database paths and model name from environment variables
db_path = os.getenv("DB_PATH")
historical_db_path = os.getenv("HISTORICAL_DB_PATH")
model_name = os.getenv("MODEL_NAME")

# Initialize the DatabaseAgent with the provided paths and model name
agent = DatabaseAgent(db_path=db_path, historical_db_path=historical_db_path, model_name=model_name)

# Initialize the FastAPI application
app = FastAPI(
    title="GTFS Database Chat Agent",
    description="A conversational agent for querying GTFS database",
    version="0.1.0"
)

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow requests from any origin
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Define the request model for the chat endpoint
class ChatRequest(BaseModel):
    """
    Request model for the chat endpoint.
    Contains the user's query and an optional session ID.
    """
    query: str
    session_id: Optional[str] = 'default'

# Define the response model for the chat endpoint
class ChatResponse(BaseModel):
    """
    Response model for the chat endpoint.
    Contains the agent's response and the session ID.
    """
    response: str
    session_id: str

# Add database validation on startup
def validate_databases():
    if not db_path or not os.path.exists(db_path):
        raise ValueError(f"Main database not found at {db_path}")
    if not historical_db_path or not os.path.exists(historical_db_path):
        raise ValueError(f"Historical database not found at {historical_db_path}")

# Add startup event
@app.on_event("startup")
async def startup_event():
    try:
        validate_databases()
    except ValueError as e:
        print(f"Database validation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Update the chat endpoint with better error handling
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Endpoint for processing chat queries with optional session tracking.
    """
    try:
        if not request.query.strip():
            raise ValueError("Query cannot be empty")
            
        response = agent.query(
            input_text=request.query, 
            session_id=request.session_id or 'default'
        )
        
        return ChatResponse(
            response=response, 
            session_id=request.session_id or 'default'
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

@app.get("/health")
async def health_check():
    """
    Health check endpoint to verify the application is running.
    
    :return: A JSON object indicating the application's health status.
    """
    return {"status": "healthy"}

if __name__ == "__main__":
    # Run the FastAPI application using Uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)