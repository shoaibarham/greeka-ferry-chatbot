"""
Travel Planning Agent - Specialized agent for creating comprehensive travel itineraries.

This agent creates multi-island itineraries, suggests island combinations based on
ferry availability, and provides comprehensive trip planning services.
"""

import os
import logging
import sqlite3
from typing import Dict, List, Optional, Any, Tuple
import re
import json
from datetime import datetime, timedelta

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

class TravelAgent:
    """
    A specialized agent that helps users create comprehensive travel itineraries.
    """
    
    def __init__(self):
        """
        Initialize the TravelAgent with specialized travel planning capabilities.
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
                "name": "run_travel_query",
                "description": "Execute an SQL query against the ferry database for trip planning",
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
                "name": "create_island_hopping_itinerary",
                "description": "Create a multi-island hopping itinerary",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_location": {
                            "type": "string",
                            "description": "The starting location (usually Athens or a major port)"
                        },
                        "num_islands": {
                            "type": "integer",
                            "description": "Number of islands to visit (2-5 recommended)"
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format"
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format"
                        },
                        "preferences": {
                            "type": "string",
                            "description": "Optional preferences like 'beaches', 'nightlife', 'culture', 'quiet'"
                        }
                    },
                    "required": ["start_location", "num_islands"]
                }
            },
            {
                "name": "suggest_island_combinations",
                "description": "Suggest island combinations that work well together based on ferry connections",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "base_port": {
                            "type": "string",
                            "description": "Base port for the island combinations (Athens, Crete, etc.)"
                        },
                        "trip_length": {
                            "type": "integer",
                            "description": "Approximate trip length in days"
                        },
                        "preferences": {
                            "type": "string",
                            "description": "Optional preferences like 'beaches', 'nightlife', 'culture', 'quiet'"
                        }
                    },
                    "required": ["base_port"]
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
                self.run_travel_query,
                self.create_island_hopping_itinerary,
                self.suggest_island_combinations
            ],
            verbose=True
        )
        
        logger.info("Travel Agent initialized successfully")
    
    def _get_system_prompt(self) -> str:
        """
        Returns the specialized system prompt for the travel planning agent.
        """
        return """
        You are a Travel Planning Specialist for FerriesinGreece, focusing exclusively on creating comprehensive travel itineraries for Greek island hopping.

        MAIN RESPONSIBILITIES:
        - Create multi-island itineraries with realistic travel times
        - Suggest combinations of islands that work well together based on ferry connections
        - Provide comprehensive trip planning with accommodation suggestions
        - Balance travel time and island exploration time in itineraries

        DATABASE STRUCTURE:
        - Main DB (gtfs.db) contains ferry routes in the 'routes' table:
          Fields: route_id, company, origin_port_name, destination_port_name,
                 departure_time, arrival_time, duration
          
        - The 'dates_and_vessels' table links routes to specific dates
          Fields: route_id, schedule_date, vessel

        ISLAND KNOWLEDGE (Use this information when suggesting islands):
        - Cyclades: Popular island group including Mykonos, Santorini, Naxos, Paros, Milos
          * Mykonos: Famous for beaches and nightlife
          * Santorini: Known for stunning caldera views and sunsets
          * Naxos: Great beaches, mountain villages, and food
          * Paros: Beautiful beaches and traditional villages
          * Milos: Known for unique landscapes and beaches
          * Syros: Cultural capital with neoclassical architecture
          * Amorgos: Remote island with dramatic landscapes
        
        - Dodecanese: Easternmost islands including Rhodes, Kos, Patmos
          * Rhodes: Medieval old town and beautiful beaches
          * Kos: Historical sites and beaches
          * Patmos: Religious significance with St. John's cave
          
        - Saronic Gulf: Close to Athens, including Aegina, Hydra, Poros
          * Aegina: Quick trip from Athens with ancient temples
          * Hydra: No cars, artistic atmosphere
          * Poros: Pine forests and beaches
          
        - Sporades: Green islands including Skiathos, Skopelos, Alonissos
          * Skiathos: Known for beaches and nightlife
          * Skopelos: 'Mamma Mia' filming location
          * Alonissos: Marine park and nature

        - Ionian Islands: Western islands including Corfu, Kefalonia, Zante
          * Corfu: Venetian influence and lush landscapes
          * Kefalonia: Diverse beaches and picturesque villages
          * Zante: Famous Shipwreck Beach

        - North Aegean: Includes Lesvos, Chios, Samos
          * Lesvos: Traditional villages and ouzo production
          * Chios: Medieval villages and mastic production
          * Samos: Beautiful beaches and sweet wine

        TRAVEL PLANNING CONSIDERATIONS:
        - Always suggest spending at least 2-3 days on each island
        - Group islands by their geographical cluster and ferry connections
        - Take into account travel time between islands (don't suggest unrealistic connections)
        - Build in buffer time for delays or missed connections
        - For first-time visitors, focus on more accessible and popular islands
        - Consider seasonal variations in ferry availability

        RESPONSE FORMAT:
        - Present itineraries day by day with clear travel instructions
        - Include approximate ferry times and durations
        - Highlight key attractions on each island
        - Suggest logical order of islands based on ferry connections
        - Provide alternative options when relevant
        
        SEARCH TIPS:
        - For Athens, check schedules from Lavrio, Rafina, and Piraeus ports
        - DB values are in CAPITAL LETTERS, use case-insensitive queries (LOWER())
        - For seasonal routes, check the dates_and_vessels table for availability
        """
    
    def run_travel_query(self, query: str) -> str:
        """
        Execute an SQL query against the ferry database for trip planning.
        
        Args:
            query: SQL query to execute
            
        Returns:
            Query results or error message
        """
        try:
            logger.info(f"Executing travel query: {query}")
            conn = sqlite3.connect(MAIN_DB_PATH)
            cursor = conn.cursor()
            cursor.execute(query)
            results = cursor.fetchall()
            conn.close()
            
            if not results:
                return "No results found for the given travel query."
            
            # Return the results as a string
            return str(results)
        except Exception as e:
            logger.error(f"Error executing travel query: {str(e)}")
            return f"Error executing travel query: {str(e)}"
    
    def create_island_hopping_itinerary(
        self, 
        start_location: str, 
        num_islands: int = 3, 
        start_date: Optional[str] = None, 
        end_date: Optional[str] = None,
        preferences: Optional[str] = None
    ) -> str:
        """
        Create a multi-island hopping itinerary.
        
        Args:
            start_location: The starting location (usually Athens or a major port)
            num_islands: Number of islands to visit
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            preferences: Optional preferences like 'beaches', 'nightlife', 'culture', 'quiet'
            
        Returns:
            A comprehensive island-hopping itinerary
        """
        logger.info(f"Creating {num_islands}-island itinerary from {start_location}")
        logger.info(f"Dates: {start_date} to {end_date}, Preferences: {preferences}")
        
        # Convert start_location to a list of ports to check
        ports_to_check = []
        if start_location.lower() in ['athens', 'athina', 'αθήνα', 'αθηνα']:
            ports_to_check = ['PIRAEUS', 'RAFINA', 'LAVRIO']
        else:
            ports_to_check = [start_location.upper()]
        
        try:
            conn = sqlite3.connect(MAIN_DB_PATH)
            cursor = conn.cursor()
            
            # Find all possible destinations from the starting location(s)
            destinations = []
            for port in ports_to_check:
                query = """
                SELECT DISTINCT
                    r.destination_port_name,
                    r.origin_port_name,
                    COUNT(DISTINCT r.route_id) as connection_count
                FROM 
                    routes r
                WHERE 
                    LOWER(r.origin_port_name) LIKE LOWER(?)
                GROUP BY
                    r.destination_port_name, r.origin_port_name
                ORDER BY
                    connection_count DESC
                """
                
                cursor.execute(query, (f'%{port}%',))
                destinations.extend(cursor.fetchall())
            
            if not destinations:
                return f"I couldn't find any ferry connections from {start_location}. Please try a different starting point."
            
            # Rank destinations by connection frequency
            all_destinations = {}
            for dest, origin, count in destinations:
                if dest not in all_destinations:
                    all_destinations[dest] = {'count': 0, 'origin': origin}
                all_destinations[dest]['count'] += count
            
            # Sort destinations by connection count
            ranked_destinations = sorted(all_destinations.items(), key=lambda x: x[1]['count'], reverse=True)
            
            # Filter for island clusters based on preferences
            possible_islands = []
            
            # Define island groups with their characteristics
            island_groups = {
                'Cyclades': {
                    'islands': ['MYKONOS', 'SANTORINI', 'NAXOS', 'PAROS', 'MILOS', 'SYROS', 'AMORGOS', 
                               'SIFNOS', 'FOLEGANDROS', 'IOS', 'TINOS', 'SERIFOS', 'KYTHNOS'],
                    'characteristics': ['beaches', 'nightlife', 'scenic', 'popular', 'traditional']
                },
                'Dodecanese': {
                    'islands': ['RHODES', 'KOS', 'PATMOS', 'LEROS', 'KALYMNOS', 'SYMI', 'TILOS', 'NISYROS'],
                    'characteristics': ['history', 'culture', 'beaches', 'quiet']
                },
                'Saronic': {
                    'islands': ['AEGINA', 'HYDRA', 'POROS', 'SPETSES', 'AGISTRI'],
                    'characteristics': ['proximity', 'day trips', 'quiet', 'culture']
                },
                'Sporades': {
                    'islands': ['SKIATHOS', 'SKOPELOS', 'ALONNISOS'],
                    'characteristics': ['green', 'beaches', 'nature']
                },
                'Ionian': {
                    'islands': ['CORFU', 'KEFALONIA', 'ZANTE', 'ITHACA', 'PAXOS'],
                    'characteristics': ['green', 'beaches', 'scenic', 'culture']
                }
            }
            
            # Filter islands based on preferences if provided
            filtered_destinations = []
            
            if preferences:
                pref_list = [p.strip().lower() for p in preferences.split(',')]
                
                # Score each island based on preferences
                for dest, info in ranked_destinations:
                    score = 0
                    for group_name, group_info in island_groups.items():
                        if any(island in dest for island in group_info['islands']):
                            # This destination is in this island group
                            for pref in pref_list:
                                if pref in group_info['characteristics']:
                                    score += 1
                    
                    if score > 0:
                        filtered_destinations.append((dest, info, score))
                
                # Sort by score, then by connection count
                filtered_destinations.sort(key=lambda x: (x[2], x[1]['count']), reverse=True)
                
                # Extract just the destination names and info
                filtered_destinations = [(dest, info) for dest, info, _ in filtered_destinations]
            else:
                # If no preferences, use the ranked destinations
                filtered_destinations = ranked_destinations
            
            # Get top islands based on num_islands parameter (add a few extra for flexibility)
            top_islands = [island for island, _ in filtered_destinations[:min(num_islands * 2, len(filtered_destinations))]]
            
            # Get inter-island connections
            connections = {}
            for island in top_islands:
                query = """
                SELECT 
                    r.destination_port_name,
                    r.departure_time,
                    r.arrival_time,
                    r.duration
                FROM 
                    routes r
                WHERE 
                    LOWER(r.origin_port_name) = LOWER(?)
                    AND LOWER(r.destination_port_name) IN ({})
                """.format(','.join(['?' for _ in top_islands]))
                
                cursor.execute(query, [island] + top_islands)
                connections[island] = cursor.fetchall()
            
            conn.close()
            
            # Build the itinerary
            response = f"🏝️ **Island Hopping Itinerary from {start_location}**\n\n"
            
            # Set dates if provided
            if start_date and end_date:
                response += f"Travel period: {start_date} to {end_date}\n\n"
                
                # Calculate total days
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                total_days = (end_dt - start_dt).days + 1
                
                if total_days < num_islands * 2:
                    response += f"⚠️ Note: Your {total_days}-day trip is a bit short for visiting {num_islands} islands. I recommend at least 2-3 days per island.\n\n"
                
            # Select the optimal islands based on connections and preferences
            selected_islands = []
            current_location = start_location.upper()
            
            # Begin with a suitable first island (well-connected from start)
            for dest, info in filtered_destinations:
                if dest not in selected_islands and dest != current_location:
                    selected_islands.append(dest)
                    break
            
            # Add subsequent islands based on connections between them
            while len(selected_islands) < num_islands:
                last_island = selected_islands[-1]
                
                # Find islands that connect well from the last selected island
                next_options = []
                if last_island in connections:
                    next_options = [dest for dest, _, _, _ in connections[last_island] 
                                   if dest not in selected_islands and dest != current_location]
                
                # If no direct connections, look for any remaining top island
                if not next_options:
                    for dest in top_islands:
                        if dest not in selected_islands and dest != current_location:
                            next_options.append(dest)
                            break
                
                # Add the next island if we found one
                if next_options:
                    selected_islands.append(next_options[0])
                else:
                    # If we can't find enough connected islands, break
                    break
            
            # Create the daily itinerary
            days_per_island = 2  # Default days per island
            
            # Adjust days per island if dates are provided
            if start_date and end_date:
                total_days = (end_dt - start_dt).days + 1
                travel_days = len(selected_islands)  # At least 1 travel day per island
                
                # Distribute remaining days
                remaining_days = total_days - travel_days
                if remaining_days > 0 and len(selected_islands) > 0:
                    days_per_island = max(1, remaining_days // len(selected_islands))
            
            # Build day-by-day itinerary
            current_day = 1
            current_date = start_dt if start_date else None
            
            # Add route from starting point to first island
            response += f"**Day {current_day}:** Depart from {start_location} to {selected_islands[0]}\n"
            response += self._get_route_details(start_location, selected_islands[0])
            
            # Add hotel/accommodation suggestion
            response += f"🏨 **Accommodation:** Stay in {selected_islands[0]} for {days_per_island} nights\n\n"
            
            # Explore the first island
            current_day += 1
            if current_date:
                current_date += timedelta(days=1)
            
            for day in range(days_per_island - 1):
                day_str = f"**Day {current_day}:** "
                if current_date:
                    day_str += f"({current_date.strftime('%Y-%m-%d')}) "
                
                response += f"{day_str}Explore {selected_islands[0]}\n"
                response += self._get_island_highlights(selected_islands[0])
                response += "\n"
                
                current_day += 1
                if current_date:
                    current_date += timedelta(days=1)
            
            # Add routes between islands
            for i in range(len(selected_islands) - 1):
                day_str = f"**Day {current_day}:** "
                if current_date:
                    day_str += f"({current_date.strftime('%Y-%m-%d')}) "
                
                response += f"{day_str}Travel from {selected_islands[i]} to {selected_islands[i+1]}\n"
                response += self._get_route_details(selected_islands[i], selected_islands[i+1])
                
                # Add hotel/accommodation suggestion
                response += f"🏨 **Accommodation:** Stay in {selected_islands[i+1]} for {days_per_island} nights\n\n"
                
                current_day += 1
                if current_date:
                    current_date += timedelta(days=1)
                
                # Explore the island
                for day in range(days_per_island - 1):
                    day_str = f"**Day {current_day}:** "
                    if current_date:
                        day_str += f"({current_date.strftime('%Y-%m-%d')}) "
                    
                    response += f"{day_str}Explore {selected_islands[i+1]}\n"
                    response += self._get_island_highlights(selected_islands[i+1])
                    response += "\n"
                    
                    current_day += 1
                    if current_date:
                        current_date += timedelta(days=1)
            
            # Add return route
            day_str = f"**Day {current_day}:** "
            if current_date:
                day_str += f"({current_date.strftime('%Y-%m-%d')}) "
            
            response += f"{day_str}Return from {selected_islands[-1]} to {start_location}\n"
            response += self._get_route_details(selected_islands[-1], start_location)
            
            # Add final summary
            response += "\n**Itinerary Summary:**\n"
            response += f"- Starting Point: {start_location}\n"
            response += f"- Islands Visited: {', '.join(selected_islands)}\n"
            response += f"- Total Duration: {current_day} days\n"
            if preferences:
                response += f"- Preferences Applied: {preferences}\n"
            
            response += "\n💡 **Travel Tips:**\n"
            response += "- Book ferry tickets in advance, especially during high season (June-September)\n"
            response += "- Arrive at the port at least 45 minutes before departure\n"
            response += "- Consider travel insurance for any ferry cancellations due to weather\n"
            response += "- Check ferry schedules again closer to your travel date as they may change\n"
            
            return response
            
        except Exception as e:
            logger.error(f"Error creating island hopping itinerary: {str(e)}")
            return f"Error creating island hopping itinerary: {str(e)}"
    
    def _get_route_details(self, origin: str, destination: str) -> str:
        """Get ferry route details between two locations."""
        try:
            conn = sqlite3.connect(MAIN_DB_PATH)
            cursor = conn.cursor()
            
            query = """
            SELECT 
                r.company, 
                r.departure_time,
                r.arrival_time,
                r.duration
            FROM 
                routes r
            WHERE 
                LOWER(r.origin_port_name) LIKE LOWER(?)
                AND LOWER(r.destination_port_name) LIKE LOWER(?)
            ORDER BY
                r.duration ASC
            LIMIT 1
            """
            
            cursor.execute(query, (f'%{origin}%', f'%{destination}%'))
            route = cursor.fetchone()
            
            conn.close()
            
            if route:
                company, departure, arrival, duration = route
                hours = duration // 60
                minutes = duration % 60
                duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
                
                return f"🚢 Ferry: {company}, Departure: {departure}, Arrival: {arrival}, Duration: {duration_str}\n"
            else:
                # If no direct connection found, suggest a general estimate
                return f"🚢 Ferry connection from {origin} to {destination} (check schedules for exact times)\n"
        except Exception as e:
            logger.error(f"Error getting route details: {str(e)}")
            return f"🚢 Ferry connection from {origin} to {destination} (check schedules for exact times)\n"
    
    def _get_island_highlights(self, island: str) -> str:
        """Get highlights and recommendations for an island."""
        island_lower = island.lower()
        
        # Highlights for popular islands
        highlights = {
            'mykonos': [
                "Visit the iconic windmills and Little Venice for sunset views",
                "Explore the charming Mykonos Town (Chora) with its white-washed buildings",
                "Relax at popular beaches like Paradise or Super Paradise"
            ],
            'santorini': [
                "Enjoy the famous sunset views from Oia",
                "Explore the caldera and volcanic islands",
                "Visit the archaeological site of Akrotiri",
                "Relax at Red Beach or Kamari Beach"
            ],
            'naxos': [
                "Visit the Portara (Temple of Apollo) for sunset views",
                "Explore the medieval castle and old town",
                "Enjoy the beautiful beaches of Agios Prokopios and Plaka",
                "Take a day trip to the mountain villages"
            ],
            'paros': [
                "Explore the charming villages of Naoussa and Parikia",
                "Visit the Byzantine church of Panagia Ekatontapiliani",
                "Relax at Golden Beach or Kolymbithres Beach"
            ],
            'rhodes': [
                "Explore the medieval Old Town and Palace of the Grand Master",
                "Visit the Acropolis of Lindos",
                "Relax at the beautiful beaches of Tsambika or Anthony Quinn Bay"
            ],
            'corfu': [
                "Explore the UNESCO-listed Old Town of Corfu",
                "Visit Achilleion Palace",
                "Enjoy the beautiful beaches of Paleokastritsa"
            ],
            'crete': [
                "Explore the Palace of Knossos near Heraklion",
                "Visit the charming old towns of Chania and Rethymno",
                "Hike the Samaria Gorge",
                "Relax at Elafonisi or Balos Beach"
            ]
        }
        
        # Generic highlights for any island
        generic_highlights = [
            "Explore the main town and its local architecture",
            "Visit the island's beaches and swimming spots",
            "Try local cuisine at traditional tavernas",
            "Explore historical sites and museums"
        ]
        
        # Find matching highlights
        selected_highlights = []
        for key, value in highlights.items():
            if key in island_lower:
                selected_highlights = value
                break
        
        # If no specific highlights found, use generic ones
        if not selected_highlights:
            selected_highlights = generic_highlights
        
        # Format the highlights
        result = "".join([f"  - {highlight}\n" for highlight in selected_highlights[:3]])
        return result
    
    def suggest_island_combinations(self, base_port: str, trip_length: int = 7, preferences: Optional[str] = None) -> str:
        """
        Suggest island combinations that work well together based on ferry connections.
        
        Args:
            base_port: Base port for the island combinations (Athens, Crete, etc.)
            trip_length: Approximate trip length in days
            preferences: Optional preferences like 'beaches', 'nightlife', 'culture', 'quiet'
            
        Returns:
            Suggested island combinations
        """
        logger.info(f"Suggesting island combinations from {base_port} for {trip_length}-day trip")
        
        # Define island groups with their characteristics
        island_groups = {
            'Cyclades': {
                'islands': ['MYKONOS', 'SANTORINI', 'NAXOS', 'PAROS', 'MILOS', 'SYROS', 'AMORGOS', 
                           'SIFNOS', 'FOLEGANDROS', 'IOS', 'TINOS', 'SERIFOS', 'KYTHNOS'],
                'characteristics': ['beaches', 'nightlife', 'scenic', 'popular', 'traditional'],
                'combinations': [
                    ['MYKONOS', 'PAROS', 'NAXOS'],
                    ['SANTORINI', 'NAXOS', 'PAROS'],
                    ['MILOS', 'SIFNOS', 'SERIFOS'],
                    ['SYROS', 'TINOS', 'MYKONOS'],
                    ['NAXOS', 'IOS', 'SANTORINI'],
                    ['PAROS', 'ANTIPAROS', 'NAXOS']
                ]
            },
            'Dodecanese': {
                'islands': ['RHODES', 'KOS', 'PATMOS', 'LEROS', 'KALYMNOS', 'SYMI', 'TILOS', 'NISYROS'],
                'characteristics': ['history', 'culture', 'beaches', 'quiet'],
                'combinations': [
                    ['RHODES', 'SYMI'],
                    ['KOS', 'KALYMNOS', 'PATMOS'],
                    ['RHODES', 'KOS', 'SYMI'],
                    ['PATMOS', 'LEROS', 'KALYMNOS']
                ]
            },
            'Saronic': {
                'islands': ['AEGINA', 'HYDRA', 'POROS', 'SPETSES', 'AGISTRI'],
                'characteristics': ['proximity', 'day trips', 'quiet', 'culture'],
                'combinations': [
                    ['HYDRA', 'SPETSES', 'POROS'],
                    ['AEGINA', 'AGISTRI', 'POROS'],
                    ['POROS', 'HYDRA']
                ]
            },
            'Sporades': {
                'islands': ['SKIATHOS', 'SKOPELOS', 'ALONNISOS'],
                'characteristics': ['green', 'beaches', 'nature'],
                'combinations': [
                    ['SKIATHOS', 'SKOPELOS'],
                    ['SKIATHOS', 'SKOPELOS', 'ALONNISOS']
                ]
            },
            'Ionian': {
                'islands': ['CORFU', 'KEFALONIA', 'ZANTE', 'ITHACA', 'PAXOS'],
                'characteristics': ['green', 'beaches', 'scenic', 'culture'],
                'combinations': [
                    ['CORFU', 'PAXOS'],
                    ['KEFALONIA', 'ITHACA'],
                    ['CORFU', 'KEFALONIA', 'ZANTE']
                ]
            }
        }
        
        try:
            # Check actual ferry connections from base_port
            conn = sqlite3.connect(MAIN_DB_PATH)
            cursor = conn.cursor()
            
            # Convert base_port to a list of ports to check
            ports_to_check = []
            if base_port.lower() in ['athens', 'athina', 'αθήνα', 'αθηνα']:
                ports_to_check = ['PIRAEUS', 'RAFINA', 'LAVRIO']
            else:
                ports_to_check = [base_port.upper()]
            
            # Find all connections from these ports
            all_connections = []
            for port in ports_to_check:
                query = """
                SELECT DISTINCT
                    r.destination_port_name
                FROM 
                    routes r
                WHERE 
                    LOWER(r.origin_port_name) LIKE LOWER(?)
                """
                
                cursor.execute(query, (f'%{port}%',))
                all_connections.extend([dest[0] for dest in cursor.fetchall()])
            
            conn.close()
            
            # Determine which island groups are accessible
            accessible_groups = {}
            for group_name, group_info in island_groups.items():
                connected_islands = [island for island in group_info['islands'] if any(island in conn for conn in all_connections)]
                
                if connected_islands:
                    accessible_groups[group_name] = {
                        'islands': connected_islands,
                        'characteristics': group_info['characteristics'],
                        'combinations': [combo for combo in group_info['combinations'] 
                                       if all(island in connected_islands for island in combo)]
                    }
            
            # Filter based on preferences if provided
            if preferences:
                pref_list = [p.strip().lower() for p in preferences.split(',')]
                
                # Score each group based on preferences
                group_scores = {}
                for group_name, group_info in accessible_groups.items():
                    score = 0
                    for pref in pref_list:
                        if pref in group_info['characteristics']:
                            score += 1
                    
                    group_scores[group_name] = score
                
                # Sort groups by score
                sorted_groups = sorted(group_scores.items(), key=lambda x: x[1], reverse=True)
                
                # Keep only the top scored groups
                accessible_groups = {name: accessible_groups[name] for name, _ in sorted_groups if _ > 0}
            
            # Determine the number of islands to visit based on trip length
            if trip_length <= 5:
                num_islands = 2
            elif trip_length <= 10:
                num_islands = 3
            else:
                num_islands = 4
            
            # Create the response
            response = f"🏝️ **Recommended Island Combinations from {base_port}**\n\n"
            
            if not accessible_groups:
                response += f"I couldn't find good island combinations accessible from {base_port} based on the ferry database.\n\n"
                
                # Provide generic combinations from Athens
                response += "Here are some popular island combinations from Athens:\n\n"
                
                response += "1. **Cyclades Classic:** Mykonos, Paros, Naxos\n"
                response += "   Perfect for: First-time visitors, beaches, mix of nightlife and relaxation\n"
                response += "   Ideal duration: 7-10 days\n\n"
                
                response += "2. **Cyclades Scenic:** Santorini, Folegandros, Milos\n"
                response += "   Perfect for: Couples, stunning landscapes, photography\n"
                response += "   Ideal duration: 8-12 days\n\n"
                
                response += "3. **Saronic Gulf Quick Trip:** Hydra, Spetses, Poros\n"
                response += "   Perfect for: Short trips, easy access from Athens\n"
                response += "   Ideal duration: 4-7 days\n\n"
                
                return response
            
            # Add combinations from the accessible groups
            count = 1
            for group_name, group_info in accessible_groups.items():
                response += f"**{group_name} Island Combinations:**\n"
                
                if not group_info['combinations']:
                    # If no predefined combinations, create some based on connected islands
                    connected = group_info['islands'][:min(num_islands, len(group_info['islands']))]
                    response += f"{count}. {', '.join(connected)}\n"
                    response += f"   Perfect for: {', '.join(group_info['characteristics'][:3])}\n"
                    response += f"   Ideal duration: {len(connected) * 3} days\n\n"
                    count += 1
                else:
                    # Use predefined combinations
                    for combo in group_info['combinations'][:2]:
                        response += f"{count}. {', '.join(combo)}\n"
                        response += f"   Perfect for: {', '.join(group_info['characteristics'][:3])}\n"
                        response += f"   Ideal duration: {len(combo) * 3} days\n\n"
                        count += 1
            
            # Add travel tips
            response += "💡 **Travel Planning Tips:**\n"
            response += f"- For a {trip_length}-day trip, I recommend visiting {num_islands} islands\n"
            response += "- Spend at least 2-3 days on each island to avoid rushing\n"
            response += "- Consider the ferry schedules between islands when planning\n"
            response += "- Book accommodations in advance during high season (June-September)\n"
            
            return response
            
        except Exception as e:
            logger.error(f"Error suggesting island combinations: {str(e)}")
            return f"Error suggesting island combinations: {str(e)}"
    
    def query(self, input_text: str, session_id: str = 'default') -> str:
        """
        Process user queries with conversational context.
        
        Args:
            input_text: User's input query
            session_id: Unique identifier for the chat session
            
        Returns:
            Agent's response
        """
        logger.info(f"Received travel planning query: '{input_text}' for session_id: {session_id}")
        
        # Initialize conversation history if it doesn't exist
        if session_id not in self.conversations:
            logger.info(f"Initializing new chat history for session: {session_id}")
            self.conversations[session_id] = []
        
        # Get conversation history
        chat_history = self.conversations[session_id]
        logger.info(f"Current history length: {len(chat_history)}")
        
        # Check if this is a direct island hopping query
        hopping_pattern = r"(?:create |plan |make |suggest |)(?:an? |)(?:island[- ]hopping|hopping|island) (?:itinerary|trip|vacation|holiday|tour)(?: from| starting from| beginning in| in)? ([A-Za-z\s\(\)]+)(?: for| with)? (\d+)(?: islands| stops)?(?:\?|\.)*$"
        hopping_match = re.match(hopping_pattern, input_text, re.IGNORECASE)
        
        if hopping_match:
            # This is a direct island hopping query
            start_location = hopping_match.group(1).strip()
            num_islands = int(hopping_match.group(2))
            
            logger.info(f"Detected island hopping query from {start_location} for {num_islands} islands")
            
            # Use the specific method for this type of query
            result = self.create_island_hopping_itinerary(start_location, num_islands)
            
            # Update chat history
            chat_history.append(HumanMessage(content=input_text))
            chat_history.append(AIMessage(content=result))
            
            return result
        
        # Check if this is a direct island combinations query
        combination_pattern = r"(?:suggest |recommend |what are |)(?:the |some |)(?:best |good |)(?:island combinations|combinations of islands|island groups)(?: from| starting from| near| in| for)? ([A-Za-z\s\(\)]+)(?:\?|\.)*$"
        combination_match = re.match(combination_pattern, input_text, re.IGNORECASE)
        
        if combination_match:
            # This is a direct island combinations query
            base_port = combination_match.group(1).strip()
            
            logger.info(f"Detected island combinations query from {base_port}")
            
            # Use the specific method for this type of query
            result = self.suggest_island_combinations(base_port)
            
            # Update chat history
            chat_history.append(HumanMessage(content=input_text))
            chat_history.append(AIMessage(content=result))
            
            return result
        
        # For any other type of query, use the regular agent flow
        logger.info("Invoking travel planning agent executor")
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
        
        logger.info("Travel planning agent response generated successfully")
        return result["output"]


# For testing
if __name__ == "__main__":
    travel_agent = TravelAgent()
    print(travel_agent.create_island_hopping_itinerary("Athens", 3))
    print(travel_agent.suggest_island_combinations("Athens", preferences="beaches, nightlife"))