import asyncio
import pyaudio
from google import genai
from google.genai import types
import sqlite3

from prompt import system_prompt


# Tools Configuration
db_path = 'gtfs.db'

# Model configuration
MODEL = "models/gemini-2.0-flash-exp"

# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024




# System instruction
SYSTEM_INSTRUCTION = types.Content(
    parts=[
        types.Part(
            text=system_prompt
        )
    ]
)

def run_sql_query(query: str) -> str:
        """
        Execute an SQL query against the database to get latest information.
        
        :param query: SQL query to execute
        :return: Query results or error message
        
        """
        forbidden_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'TRUNCATE']
        if any(keyword in query.upper() for keyword in forbidden_keywords):
            return "Error: Potentially dangerous SQL query detected."
        
        try:
            print(f"Executing query: {query}")
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(query)
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
                    
            conn.close()
            
            if not rows:
                return "No results found."
            
            result_str = "Columns: " + ", ".join(columns) + "\n"
            result_str += "\n".join([str(row) for row in rows])
            
            print(f"Result: {result_str}")
            return result_str
        
        except sqlite3.Error as e:
            return f"Database error: {e}"
        except Exception as e:
            return f"Unexpected error executing query: {e}"

available_functions = {
    "run_sql_query":  run_sql_query,
}   

# Session configuration
CONFIG = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    system_instruction=SYSTEM_INSTRUCTION,
    tools=[run_sql_query],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")
        )
    )
)
# Voices : Charon , Puck , Kore , Fenrir , Aoede

# Initialize PyAudio
pya = pyaudio.PyAudio()

class VoiceAssistant:
    def __init__(self):
        self.audio_in_queue = None
        self.out_queue = None
        self.session = None
        self.client = genai.Client(http_options={"api_version": "v1alpha"} , api_key="AIzaSyDfSvQXOtHa0FAlkzyYVrqvql79510y1tM")
        
    def handle_function_call(self, response, available_functions):
        """
        Dynamically handles function calls from the model response.
        
        Args:
            response: The response object containing tool_call information
            available_functions: A dictionary mapping function names to function objects
            
        Returns:
            The result of the function call or an error message
        """
        try:
            if hasattr(response, 'tool_call') and response.tool_call:
                if hasattr(response.tool_call, 'function_calls') and response.tool_call.function_calls:
                    # Get the first function call
                    tool_call = response.tool_call.function_calls[0]
                    function_name = tool_call.name
                    args = tool_call.args
                    
                    print(f"Function: {function_name}, Args: {args}")
                    
                    if function_name in available_functions:
                        function_to_call = available_functions[function_name]
                        
                        # Call the function with the provided arguments
                        try:
                            return function_to_call(**args)
                        except Exception as e:
                            return f"Error calling {function_name}: {str(e)}"
                    else:
                        return f"Function '{function_name}' does not exist"
                
            return "No valid function call found in the response"
        
        except Exception as e:
            return f"Error processing function call: {str(e)}"

    async def listen_audio(self):
        """Captures real-time audio input from microphone"""
        mic_info = pya.get_default_input_device_info()
        self.audio_stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=SEND_SAMPLE_RATE,
            input=True,
            input_device_index=mic_info["index"],
            frames_per_buffer=CHUNK_SIZE,
        )
        
        while True:
            data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE)
            await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})

    async def send_audio(self):
        """Sends audio data to the Gemini API"""
        while True:
            audio_data = await self.out_queue.get()
            if self.session:
                await self.session.send(input=audio_data, end_of_turn=True)
                    

    async def receive_and_process(self):
        try:
            """Receives responses and handles tool calls"""
            while True:
                turn = self.session.receive()
                async for response in turn:
                    if data := response.data:
                        self.audio_in_queue.put_nowait(data)
                    
                    # Handle tool calls
                    if response.tool_call:
                        print("Tool call detected")
                        result = self.handle_function_call(response, available_functions)
                        await self.session.send(input=result, end_of_turn=True)
                    
                    # Handle interruptions
                    if response.server_content and response.server_content.interrupted is not None:
                        print("Response interrupted by user")
                        while not self.audio_in_queue.empty():
                            self.audio_in_queue.get_nowait()
                            
        except Exception as e:
            print(f"Error in receive_and_process: {e}")

    async def play_audio(self):
        """Plays received audio in real-time"""
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )
        while True:
            bytestream = await self.audio_in_queue.get()
            await asyncio.to_thread(stream.write, bytestream)

    async def run(self):
        """Main execution loop"""
        try:
            async with (
                self.client.aio.live.connect(model=MODEL, config=CONFIG) as session,
                asyncio.TaskGroup() as tg,
            ):
                self.session = session
                self.audio_in_queue = asyncio.Queue()
                self.out_queue = asyncio.Queue(maxsize=5)

                # Start all tasks
                tg.create_task(self.listen_audio())
                tg.create_task(self.send_audio())
                tg.create_task(self.receive_and_process())
                tg.create_task(self.play_audio())

                # Keep running until interrupted
                await asyncio.Future()  # Runs indefinitely until cancelled

        except asyncio.CancelledError:
            print("Session terminated by user")
        except Exception as e:
            print(f"An error occurred: {str(e)}")
        finally:
            if hasattr(self, 'audio_stream'):
                self.audio_stream.close()

if __name__ == "__main__":
    assistant = VoiceAssistant()
    try:
        asyncio.run(assistant.run())
    except KeyboardInterrupt:
        print("\nStopped by user")