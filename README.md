# Greek Ferry Chatbot

A production-level Greek Ferry Information Chatbot using Gemini 2.0 with Flask backend and LangChain agents for accurate ferry route, schedule, and pricing information.

## Overview

This chatbot provides information about ferry routes, schedules, and prices between Greek islands. It uses Google's Gemini AI model with LangChain agents for natural language processing and a PostgreSQL database to store ferry information.

Key features:
- Natural language understanding of ferry-related queries
- Detailed information about routes, schedules, and prices
- Multi-segment journey planning
- Daily data updates to ensure accurate information
- Admin interface for monitoring and manual updates

## Architecture

The application consists of several components:

1. **Web Interface**: A responsive Flask web application with a chat interface
2. **Agent System**: LangChain agents using Google's Gemini model for query processing
3. **Database**: PostgreSQL database storing ferry information
4. **Data Updater**: Scheduled daily data updates to maintain accuracy
5. **Admin Panel**: Interface for monitoring database status and performing manual updates

## Data Structure

The database includes the following main tables:
- `ferry_companies`: Information about ferry operators
- `ports`: Information about ports
- `vessels`: Information about ferry vessels
- `ferry_routes`: Details of ferry routes
- `schedules`: Specific sailing dates
- `accommodations`: Available accommodation types on vessels

## Setup and Installation

### Prerequisites
- Python 3.8+
- PostgreSQL database
- Google Gemini API key

### Environment Variables
- `GEMINI_API_KEY`: Your Google Gemini API key
- `SESSION_SECRET`: Secret key for Flask sessions
- `DATABASE_URL`: PostgreSQL database connection URL

### Installation

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Configure environment variables
4. Initialize the database:
   ```
   python data_updater.py
   ```
5. Start the application:
   ```
   python main.py
   ```

## Usage

### Chatbot Interface
- Access the chatbot at `/`
- Ask questions about ferry routes, schedules, and prices
- Example queries:
  - "Are there any ferries from Milos to Kimolos on March 23, 2025?"
  - "What's the cheapest ferry from Piraeus to Sifnos next week?"
  - "I want to go from Milos to Piraeus with a stop in Sifnos."

### Admin Interface
- Access the admin panel at `/admin`
- View database status and record counts
- Trigger manual data updates
- Monitor update history

## Data Update Process

The ferry data is automatically updated daily at 3:00 AM to ensure accuracy. This process:
1. Downloads the latest ferry data
2. Processes and validates the data
3. Updates the database while maintaining data integrity
4. Logs the update process

Manual updates can be triggered through the admin interface.

## API Endpoints

- `/api/chat`: Process user queries (POST)
- `/api/update_data`: Trigger data updates (POST)
- `/api/ports`: Get a list of available ports (GET)
- `/api/database-status`: Get database status information (GET)

## Future Enhancements

Potential future improvements include:
- Multi-language support
- User account management for saved searches and booking history
- Ticketing and reservation integration
- Mobile application
- Voice interface support
- Historical data analysis for price trends