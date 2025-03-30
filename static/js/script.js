// Constants
const API_ENDPOINT = '/api/chat';
let conversationId = null;

// DOM elements
const messagesContainer = document.getElementById('messages');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  // Focus the input field on page load
  messageInput.focus();
  
  // Add event listeners
  messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  
  sendButton.addEventListener('click', sendMessage);
  
  // Add initial greeting from assistant
  addMessage('Welcome to the Greek Ferry Chatbot! How can I help you with your ferry travel plans today?', 'assistant');
});

// Function to send user message to the API
async function sendMessage() {
  const userMessage = messageInput.value.trim();
  
  // Don't send empty messages
  if (!userMessage) return;
  
  // Add user message to the chat
  addMessage(userMessage, 'user');
  
  // Clear input
  messageInput.value = '';
  
  // Show loading indicator
  const loadingIndicator = addLoadingIndicator();
  
  try {
    // Prepare request data
    const requestData = {
      message: userMessage
    };
    
    // Add conversation ID if it exists
    if (conversationId) {
      requestData.conversation_id = conversationId;
    }
    
    // Send API request
    const response = await fetch(API_ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(requestData)
    });
    
    // Parse response
    const data = await response.json();
    
    // Remove loading indicator
    loadingIndicator.remove();
    
    if (data.error) {
      // Handle error
      addMessage(`Sorry, an error occurred: ${data.error}`, 'assistant');
    } else {
      // Save conversation ID
      conversationId = data.conversation_id;
      
      // Add assistant response
      addMessage(formatResponseText(data.response), 'assistant');
    }
  } catch (error) {
    // Remove loading indicator
    loadingIndicator.remove();
    
    // Add error message
    addMessage('Sorry, there was an error communicating with the server. Please try again.', 'assistant');
    console.error('Error sending message:', error);
  }
  
  // Scroll to bottom
  scrollToBottom();
}

// Function to add a message to the chat
function addMessage(text, sender) {
  const messageElement = document.createElement('div');
  messageElement.classList.add('message', `message-${sender}`);
  
  // Format the message content
  messageElement.innerHTML = formatMessageContent(text);
  
  // Add metadata (timestamp)
  const now = new Date();
  const timeString = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  
  const metadataElement = document.createElement('div');
  metadataElement.classList.add('message-metadata');
  metadataElement.textContent = timeString;
  
  messageElement.appendChild(metadataElement);
  
  // Add to messages container
  messagesContainer.appendChild(messageElement);
  
  // Scroll to bottom
  scrollToBottom();
  
  return messageElement;
}

// Function to format message content with line breaks and ferry details
function formatMessageContent(text) {
  // Convert line breaks to <br> tags
  let formattedText = text.replace(/\n/g, '<br>');
  
  // Enhance ferry route information
  formattedText = formatFerryRoutes(formattedText);
  
  return formattedText;
}

// Function to add loading indicator
function addLoadingIndicator() {
  const loadingElement = document.createElement('div');
  loadingElement.classList.add('message', 'message-assistant', 'loading-indicator');
  
  loadingElement.innerHTML = `
    <div class="dot"></div>
    <div class="dot"></div>
    <div class="dot"></div>
  `;
  
  messagesContainer.appendChild(loadingElement);
  scrollToBottom();
  
  return loadingElement;
}

// Function to scroll to the bottom of the messages container
function scrollToBottom() {
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Function to format ferry route information in responses
function formatFerryRoutes(text) {
  // This is a simple format detection - in a real app, we'd use more sophisticated
  // pattern matching or structured data from the backend
  
  // Look for patterns that indicate ferry route information
  const lines = text.split('<br>');
  let inFerryRoute = false;
  let routeStartIndex = -1;
  let routeEndIndex = -1;
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    
    // Detect start of ferry route information
    if (line.includes('Departure:') && line.includes('at') && !inFerryRoute) {
      inFerryRoute = true;
      routeStartIndex = i - 1 >= 0 && lines[i - 1].includes('found') ? i - 1 : i;
    }
    
    // Detect end of ferry route information
    if (inFerryRoute && (
      (line.trim() === '' && i > routeStartIndex + 3) || 
      line.includes('Would you like') ||
      i === lines.length - 1
    )) {
      routeEndIndex = line.trim() === '' ? i - 1 : i;
      
      // Extract and format the ferry route
      const routeLines = lines.slice(routeStartIndex, routeEndIndex + 1);
      const formattedRoute = formatSingleFerryRoute(routeLines);
      
      // Replace the original lines with the formatted route
      lines.splice(routeStartIndex, routeEndIndex - routeStartIndex + 1, formattedRoute);
      
      // Reset for the next route
      inFerryRoute = false;
      i = routeStartIndex; // Adjust the index to continue from the correct position
    }
  }
  
  return lines.join('<br>');
}

// Function to format a single ferry route into a nicer HTML structure
function formatSingleFerryRoute(routeLines) {
  // Extract key information (simplified - would be more robust in a real app)
  let origin, destination, date, departureTime, arrivalTime, duration, company, vessel, price, accommodations = [];
  
  routeLines.forEach(line => {
    if (line.includes('Date:')) {
      date = line.split('Date:')[1].trim();
    } else if (line.includes('Departure:')) {
      const parts = line.split('Departure:')[1].trim().split(' at ');
      origin = parts[0];
      departureTime = parts[1];
    } else if (line.includes('Arrival:')) {
      const parts = line.split('Arrival:')[1].trim().split(' at ');
      destination = parts[0];
      arrivalTime = parts[1];
    } else if (line.includes('Duration:')) {
      duration = line.split('Duration:')[1].trim();
    } else if (line.includes('Company:')) {
      company = line.split('Company:')[1].trim();
    } else if (line.includes('Vessel:')) {
      vessel = line.split('Vessel:')[1].trim();
    } else if (line.includes('Base fare:')) {
      price = line.split('Base fare:')[1].trim();
    } else if (line.includes('-') && line.includes('€')) {
      // This looks like an accommodation option
      const parts = line.split(':');
      if (parts.length > 1) {
        const name = parts[0].replace('-', '').trim();
        const price = parts[1].trim();
        accommodations.push({ name, price });
      }
    }
  });
  
  // If we couldn't extract the needed information, return the original text
  if (!origin || !destination || !departureTime || !arrivalTime) {
    return routeLines.join('<br>');
  }
  
  // Create formatted HTML
  return `
    <div class="ferry-route">
      <div class="ferry-route-header">
        <div class="ferry-route-title">${origin} to ${destination}</div>
        <div class="ferry-route-company">${company || ''} ${vessel ? '- ' + vessel : ''}</div>
      </div>
      <div class="ferry-route-details">
        <div class="ferry-route-times">
          <div class="departure">
            <div class="time">${departureTime}</div>
            <div class="port">${origin}</div>
          </div>
          <div class="duration">
            <div class="duration-line"></div>
            <div class="duration-time">${duration}</div>
          </div>
          <div class="arrival">
            <div class="time">${arrivalTime}</div>
            <div class="port">${destination}</div>
          </div>
        </div>
        <div class="ferry-route-price">
          ${price || ''}
        </div>
      </div>
      ${date ? `<div>Date: ${date}</div>` : ''}
      ${accommodations.length > 0 ? `
        <div class="accommodations-list">
          <div style="font-weight: bold; margin-top: 8px;">Accommodation options:</div>
          ${accommodations.map(acc => `
            <div class="accommodation-item">
              <div>${acc.name}</div>
              <div>${acc.price}</div>
            </div>
          `).join('')}
        </div>
      ` : ''}
    </div>
  `;
}

// Function to format the response text for better readability
function formatResponseText(text) {
  // This is a placeholder for any additional text formatting
  // needed before applying the HTML formatting
  return text;
}
