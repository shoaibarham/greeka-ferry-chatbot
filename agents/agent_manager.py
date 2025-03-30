"""
Agent Manager - Central coordinator for all specialized agents in the ferry information system.

This module provides a unified interface for accessing all specialized agents and
determines which agent should handle specific types of queries.
"""

import os
import logging
import re
from typing import Dict, Optional, List, Any

# Import specialized agents
from agents.route_agent import RouteAgent
from agents.price_agent import PriceAgent
from agents.schedule_agent import ScheduleAgent
from agents.travel_agent import TravelAgent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgentManager:
    """
    Central manager for all specialized agents in the system.
    
    This class provides a unified interface for accessing specialized agents
    and determines which agent should handle specific types of queries.
    """
    
    def __init__(self):
        """
        Initialize the AgentManager with all specialized agents.
        """
        logger.info("Initializing Agent Manager with specialized agents")
        
        # Initialize agents (lazy loading to avoid unnecessary resource usage)
        self._route_agent = None
        self._price_agent = None
        self._schedule_agent = None
        self._travel_agent = None
        
        # Define regex patterns for query categorization
        self.patterns = {
            'route': [
                r'(ferry|ferries|boat|route|connection|transportation).*?(?:from|between)\s+([A-Za-z\s\(\)]+)\s+(?:to|and)\s+([A-Za-z\s\(\)]+)',
                r'(?:how|can)\s+(?:do|to|i)\s+(?:i|we)?\s*get\s+(?:from|between)\s+([A-Za-z\s\(\)]+)\s+(?:to|and)\s+([A-Za-z\s\(\)]+)',
                r'([A-Za-z\s\(\)]+)\s+to\s+([A-Za-z\s\(\)]+)'  # Simple "Origin to Destination" format
            ],
            'price': [
                r'(?:how much|cost|price|fare|ticket price|ticket cost).*?(?:from|between)\s+([A-Za-z\s\(\)]+)\s+(?:to|and)\s+([A-Za-z\s\(\)]+)',
                r'(?:cheapest|least expensive|affordable|budget).*?(?:from|to|between)\s+([A-Za-z\s\(\)]+)',
                r'(?:compare|comparison).*?(?:price|cost|fare).*?(?:from|between)\s+([A-Za-z\s\(\)]+)\s+(?:to|and)\s+([A-Za-z\s\(\)]+)'
            ],
            'schedule': [
                r'(?:schedule|timetable|departure|arrival|time|when).*?(?:from|between)\s+([A-Za-z\s\(\)]+)\s+(?:to|and)\s+([A-Za-z\s\(\)]+)',
                r'(?:earliest|latest|fastest|next).*?(?:ferry|boat|route|connection).*?(?:from|between)\s+([A-Za-z\s\(\)]+)\s+(?:to|and)\s+([A-Za-z\s\(\)]+)',
                r'(?:how long|duration|travel time|journey time).*?(?:from|between)\s+([A-Za-z\s\(\)]+)\s+(?:to|and)\s+([A-Za-z\s\(\)]+)'
            ],
            'travel': [
                r'(?:island hopping|itinerary|vacation|holiday|trip).*?(?:from|starting from|beginning|in)\s+([A-Za-z\s\(\)]+)',
                r'(?:plan|create|suggest|recommend).*?(?:trip|vacation|itinerary|holiday)',
                r'(?:island combination|combine islands|multiple islands|several islands|visit islands)'
            ]
        }
        
        logger.info("Agent Manager initialized successfully")
    
    @property
    def route_agent(self) -> RouteAgent:
        """Lazy-load the route agent."""
        if self._route_agent is None:
            logger.info("Initializing Route Agent")
            self._route_agent = RouteAgent()
        return self._route_agent
    
    @property
    def price_agent(self) -> PriceAgent:
        """Lazy-load the price agent."""
        if self._price_agent is None:
            logger.info("Initializing Price Agent")
            self._price_agent = PriceAgent()
        return self._price_agent
    
    @property
    def schedule_agent(self) -> ScheduleAgent:
        """Lazy-load the schedule agent."""
        if self._schedule_agent is None:
            logger.info("Initializing Schedule Agent")
            self._schedule_agent = ScheduleAgent()
        return self._schedule_agent
    
    @property
    def travel_agent(self) -> TravelAgent:
        """Lazy-load the travel agent."""
        if self._travel_agent is None:
            logger.info("Initializing Travel Agent")
            self._travel_agent = TravelAgent()
        return self._travel_agent
    
    def categorize_query(self, query_text: str) -> str:
        """
        Determine which category a query belongs to.
        
        Args:
            query_text: The user's query text
            
        Returns:
            Category name ('route', 'price', 'schedule', 'travel', or 'general')
        """
        query_lower = query_text.lower()
        
        # Check against each category's patterns
        for category, pattern_list in self.patterns.items():
            for pattern in pattern_list:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    logger.info(f"Query categorized as: {category}")
                    return category
        
        # If no patterns match, return 'general'
        logger.info("Query categorized as: general")
        return 'general'
    
    def process_query(self, query_text: str, session_id: str = 'default') -> str:
        """
        Process a user query by routing it to the appropriate specialized agent.
        
        Args:
            query_text: The user's query text
            session_id: Unique identifier for the conversation session
            
        Returns:
            The agent's response
        """
        logger.info(f"Processing query: '{query_text}' (session: {session_id})")
        
        # Categorize the query
        category = self.categorize_query(query_text)
        
        # Route to the appropriate agent
        if category == 'route':
            logger.info("Routing to Route Agent")
            return self.route_agent.query(query_text, session_id)
        elif category == 'price':
            logger.info("Routing to Price Agent")
            return self.price_agent.query(query_text, session_id)
        elif category == 'schedule':
            logger.info("Routing to Schedule Agent")
            return self.schedule_agent.query(query_text, session_id)
        elif category == 'travel':
            logger.info("Routing to Travel Agent")
            return self.travel_agent.query(query_text, session_id)
        else:
            # For general queries, try to find the most appropriate agent based on keywords
            if any(word in query_text.lower() for word in ['cheapest', 'price', 'cost', 'fare', 'ticket', 'expensive']):
                logger.info("Routing general query to Price Agent based on keywords")
                return self.price_agent.query(query_text, session_id)
            elif any(word in query_text.lower() for word in ['time', 'schedule', 'departure', 'arrival', 'when', 'fastest']):
                logger.info("Routing general query to Schedule Agent based on keywords")
                return self.schedule_agent.query(query_text, session_id)
            elif any(word in query_text.lower() for word in ['island', 'vacation', 'holiday', 'itinerary', 'trip', 'visit']):
                logger.info("Routing general query to Travel Agent based on keywords")
                return self.travel_agent.query(query_text, session_id)
            else:
                # Default to route agent for general transportation queries
                logger.info("Routing general query to Route Agent (default)")
                return self.route_agent.query(query_text, session_id)


# Singleton instance
_instance = None

def get_agent_manager() -> AgentManager:
    """
    Get the singleton instance of the AgentManager.
    
    Returns:
        The AgentManager instance
    """
    global _instance
    if _instance is None:
        _instance = AgentManager()
    return _instance


# For testing
if __name__ == "__main__":
    manager = get_agent_manager()
    
    # Test some queries
    test_queries = [
        "How do I get from Piraeus to Mykonos?",
        "What is the price of a ferry from Athens to Santorini?",
        "When does the earliest ferry depart from Rafina to Tinos?",
        "Can you suggest an island hopping itinerary from Athens?",
        "Tell me about Greek ferries",
    ]
    
    for query in test_queries:
        category = manager.categorize_query(query)
        print(f"Query: '{query}' -> Category: {category}")