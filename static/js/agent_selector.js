/**
 * Agent Selector - JavaScript module for selecting specialized agent types
 * 
 * This module provides functionality for selecting and using different
 * specialized agents in the ferry chatbot system.
 */

// Available agent types
const agentTypes = {
    'auto': 'Auto-detect (Default)',
    'route': 'Route Finding Agent',
    'price': 'Price Comparison Agent',
    'schedule': 'Schedule Optimization Agent',
    'travel': 'Travel Planning Agent'
};

// Agent descriptions
const agentDescriptions = {
    'auto': 'Automatically selects the most appropriate agent based on your query.',
    'route': 'Specialized in finding routes between locations with comprehensive information.',
    'price': 'Focused on finding the cheapest tickets and comparing prices across vessels.',
    'schedule': 'Helps you find optimal travel times and alternative routes with better schedules.',
    'travel': 'Creates multi-island itineraries and suggests island combinations for vacations.'
};

// Agent examples
const agentExamples = {
    'auto': [
        'How do I get from Piraeus to Mykonos?',
        'What are the cheapest tickets to Santorini?',
        'When is the earliest ferry from Rafina to Tinos?',
        'Can you suggest an island hopping itinerary?'
    ],
    'route': [
        'How do I get from Piraeus to Mykonos?',
        'Is there a ferry between Crete and Rhodes?',
        'Brindisi to Corfu',
        'What routes connect Athens to Hydra?'
    ],
    'price': [
        'What are the cheapest tickets to Santorini?',
        'Compare prices from Piraeus to Mykonos',
        'How much does it cost to go from Rafina to Tinos?',
        'Cheapest destinations from Athens'
    ],
    'schedule': [
        'When is the earliest ferry from Rafina to Tinos?',
        'Latest departure from Piraeus to Mykonos',
        'Fastest route to Santorini',
        'Can I make a connection from Mykonos to Naxos to Santorini in one day?'
    ],
    'travel': [
        'Plan an island hopping trip from Athens',
        'Suggest a 10-day itinerary visiting 3 islands',
        'Which islands combine well with Mykonos?',
        'Island hopping in the Cyclades'
    ]
};

// Current selected agent type
let currentAgentType = 'auto';

/**
 * Initialize the agent selector UI
 */
function initAgentSelector() {
    // Create the agent selector UI
    const chatContainer = document.querySelector('.chat-container');
    if (!chatContainer) return;
    
    // Create the agent selector dropdown
    const selectorContainer = document.createElement('div');
    selectorContainer.className = 'agent-selector-container';
    selectorContainer.innerHTML = `
        <div class="agent-selector">
            <label for="agent-type">Agent Type:</label>
            <select id="agent-type" class="form-select">
                ${Object.entries(agentTypes).map(([key, value]) => 
                    `<option value="${key}">${value}</option>`
                ).join('')}
            </select>
            <button id="agent-info-toggle" class="btn btn-sm btn-outline-info">
                <i class="fas fa-info-circle"></i>
            </button>
        </div>
        <div class="agent-info" style="display: none;">
            <div class="agent-description"></div>
            <div class="example-queries">
                <h6>Example Queries:</h6>
                <ul class="example-list"></ul>
            </div>
        </div>
    `;
    
    // Insert the selector before the chat form
    const chatForm = document.querySelector('#chat-form');
    chatContainer.insertBefore(selectorContainer, chatForm);
    
    // Set up event listeners
    const agentSelect = document.querySelector('#agent-type');
    const infoToggle = document.querySelector('#agent-info-toggle');
    const agentInfo = document.querySelector('.agent-info');
    const agentDescription = document.querySelector('.agent-description');
    const exampleList = document.querySelector('.example-list');
    
    // Agent selection change event
    agentSelect.addEventListener('change', function() {
        currentAgentType = this.value;
        updateAgentInfo();
    });
    
    // Info toggle click event
    infoToggle.addEventListener('click', function() {
        agentInfo.style.display = agentInfo.style.display === 'none' ? 'block' : 'none';
    });
    
    // Example query click event
    exampleList.addEventListener('click', function(e) {
        if (e.target.tagName === 'LI') {
            const messageInput = document.querySelector('#message-input');
            if (messageInput) {
                messageInput.value = e.target.textContent;
                messageInput.focus();
            }
        }
    });
    
    // Initial update of agent info
    updateAgentInfo();
    
    // Add CSS for agent selector
    addAgentSelectorStyles();
}

/**
 * Update the agent info section based on the current selection
 */
function updateAgentInfo() {
    const agentDescription = document.querySelector('.agent-description');
    const exampleList = document.querySelector('.example-list');
    
    // Update description
    agentDescription.textContent = agentDescriptions[currentAgentType];
    
    // Update examples
    exampleList.innerHTML = '';
    agentExamples[currentAgentType].forEach(example => {
        const li = document.createElement('li');
        li.textContent = example;
        li.className = 'example-query';
        exampleList.appendChild(li);
    });
}

/**
 * Add CSS styles for the agent selector
 */
function addAgentSelectorStyles() {
    const style = document.createElement('style');
    style.textContent = `
        .agent-selector-container {
            margin-bottom: 15px;
            background-color: var(--bs-gray-800);
            border-radius: 8px;
            padding: 12px;
        }
        
        .agent-selector {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .agent-selector label {
            margin-bottom: 0;
            white-space: nowrap;
            color: var(--bs-light);
        }
        
        .agent-selector select {
            flex-grow: 1;
            background-color: var(--bs-gray-700);
            color: var(--bs-light);
            border-color: var(--bs-gray-600);
        }
        
        .agent-info {
            margin-top: 10px;
            background-color: var(--bs-gray-700);
            border-radius: 8px;
            padding: 10px;
        }
        
        .agent-description {
            margin-bottom: 10px;
            color: var(--bs-light);
        }
        
        .example-queries h6 {
            color: var(--bs-info);
            margin-bottom: 5px;
        }
        
        .example-list {
            list-style-type: none;
            padding-left: 0;
        }
        
        .example-query {
            cursor: pointer;
            margin-bottom: 5px;
            color: var(--bs-light);
            padding: 5px;
            border-radius: 4px;
            transition: background-color 0.2s;
        }
        
        .example-query:hover {
            background-color: var(--bs-gray-600);
        }
    `;
    document.head.appendChild(style);
}

/**
 * Get the current selected agent type to include in API requests
 */
function getCurrentAgentType() {
    return currentAgentType;
}

/**
 * Add agent type to the chat API request
 */
function addAgentToRequest(data) {
    data.agent_type = getCurrentAgentType();
    return data;
}

// Initialize when the document is ready
document.addEventListener('DOMContentLoaded', initAgentSelector);

// Export the functions for use in script.js
window.agentSelector = {
    getCurrentAgentType,
    addAgentToRequest
};