import os
import sys
import json
import threading
import websocket
import pyaudio
import base64
import signal
import asyncio
import queue
from dotenv import load_dotenv
from timeline import Timeline

load_dotenv()

WEBSOCKET_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
AUDIO_FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 24000
CHUNK = 1024
interrupted = False

def signal_handler(sig, frame):
    global interrupted
    interrupted = True
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

class AudioPlayer:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=AUDIO_FORMAT,
                                  channels=CHANNELS,
                                  rate=RATE,
                                  output=True,
                                  frames_per_buffer=CHUNK)
        self.lock = threading.Lock()
        self.audio_queue = queue.Queue()
        self.is_playing = True
        self.playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
        self.playback_thread.start()
        
    def _playback_worker(self):
        while self.is_playing:
            try:
                audio_chunk = self.audio_queue.get(timeout=0.1)
                with self.lock:
                    self.stream.write(audio_chunk)
            except queue.Empty:
                continue
            
    def play_audio(self, audio_bytes):
        if self.is_playing:
            self.audio_queue.put(audio_bytes)
            
    def flush(self):
        with self.lock:
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    break
            self.stream.stop_stream()
            self.stream.start_stream()
            
    def close(self):
        self.is_playing = False
        if self.playback_thread.is_alive():
            self.playback_thread.join()
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()

class AudioSender:
    def __init__(self, ws):
        self.ws = ws
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=AUDIO_FORMAT,
                                  channels=CHANNELS,
                                  rate=RATE,
                                  input=True,
                                  frames_per_buffer=CHUNK)
        self.thread = threading.Thread(target=self.send_audio, daemon=True)
        self.running = False
    def start(self):
        self.running = True
        self.thread.start()
    def send_audio(self):
        try:
            while self.running and not interrupted:
                data = self.stream.read(CHUNK, exception_on_overflow=False)
                audio_base64 = base64.b64encode(data).decode('utf-8')
                audio_event = {
                    "type": "input_audio_buffer.append",
                    "audio": audio_base64
                }
                self.ws.send(json.dumps(audio_event))
        except Exception:
            self.running = False
    def commit_buffer(self):
        commit_event = {"type": "input_audio_buffer.commit"}
        self.ws.send(json.dumps(commit_event))
    def stop(self):
        self.running = False
        self.commit_buffer()
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()

class ChatStreaming:
    def __init__(self, api_key):
        self.api_key = api_key
        self.ws = None
        self.audio_player = AudioPlayer()
        self.audio_sender = None
        self.timeline = Timeline()
        self.instructions = (
            "You are a helpful assistant designed to catch the user up on their bluesky timeline. You speak quickly and casually, very cheerful and with lots of emotion appropriate to the context.\n"
            "You have access to the following functions:\n"
            "1. get_page_summary(page: int): Returns a summary of the posts on the given page number.\n"
            "2. get_post_detail(post_number: int): Returns detailed information about the post with the given post number.\n"
            "Start by getting the first page and then summarizing anything interesting in it. Keep your answers concise be curious."
        )

    def send_response_create(self):
        response_create_event = {
            "type": "response.create",
            "response": {
                "modalities": ["text","audio"],
                "instructions": self.instructions
            }
        }
        self.ws.send(json.dumps(response_create_event))

    def on_open(self, ws):
        print("WebSocket connection established")
        self.audio_sender = AudioSender(ws)
        self.audio_sender.start()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.timeline.initialize())
        session_update_event = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": self.instructions,
                "input_audio_transcription": {"model": "whisper-1"},
                "tools": [
                    {
                        "type": "function",
                        "name": "get_page_summary",
                        "description": "Returns a summary of the posts on the given page number.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "page": {
                                    "type": "integer",
                                    "description": "The page number to get the summary for."
                                }
                            },
                            "required": ["page"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "get_post_detail",
                        "description": "Returns detailed information about the post with the given post number.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "post_number": {
                                    "type": "integer",
                                    "description": "The post number to get details for."
                                }
                            },
                            "required": ["post_number"]
                        }
                    }
                ],
                "tool_choice": "auto",
                "voice": "echo",
                "temperature": 0.7
            }
        }
        ws.send(json.dumps(session_update_event))
        self.send_response_create()

    def on_message(self, ws, message):
        try:
            event = json.loads(message)
            event_type = event.get("type")

            if event_type == "input_audio_buffer.speech_started":
                self.audio_player.flush()
            elif event_type == "response.function_call_arguments.done":
                function_name = event.get("name")
                arguments = event.get("arguments")
                args = json.loads(arguments)
                result = self.execute_function(function_name, args)
                print(f"Function result: {json.dumps(result, indent=2)}\n")
                function_call_output_event = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": event.get("call_id"),
                        "output": json.dumps(result)
                    }
                }
                print(f"Sending: {json.dumps(function_call_output_event, indent=2)}")
                ws.send(json.dumps(function_call_output_event))
                self.send_response_create()  # Add new response after function result
            elif event_type == "response.audio.delta":
                audio_base64 = event.get("delta", "")
                if audio_base64:
                    audio_bytes = base64.b64decode(audio_base64)
                    threading.Thread(target=self.audio_player.play_audio, args=(audio_bytes,), daemon=True).start()
            elif event_type == "response.audio_transcript.done":
                transcript = event.get("transcript", "")
                if transcript:
                    print(f"\nAssistant (Transcript): {transcript}\n")
            elif event_type == "response.output_item.added":
                output_item = event.get("output_item", {})
                content = output_item.get("content", {})
                modality = content.get("type")
                if modality == "text":
                    text = content.get("text", "")
                    if text:
                        print(f"\nAssistant: {text}\n")
            elif event_type == "error":
                print(f"Error occurred: {json.dumps(event, indent=2)}")
            else:
                print(f"Unhandled event: {event_type}")
        except Exception:
            pass
    def execute_function(self, function_name, args):
        print(f"\nExecuting function: {function_name}({json.dumps(args, indent=2)})")
        try:
            result = None
            if function_name == "get_page_summary":
                page = args.get("page", 1)
                minimal_posts = self.timeline.get_minimal_posts(page=page)
                result = {"status": "success", "message": minimal_posts}
            elif function_name == "get_post_detail":
                post_number = args.get("post_number", 1)
                detailed_post = self.timeline.get_post_detail(post_number=post_number)
                result = {"status": "success", "message": detailed_post}
            else:
                result = {"status": "error", "message": f"Unknown function: {function_name}"}
            return result
        except Exception as e:
            error_result = {"status": "error", "message": str(e)}
            print(f"Function error: {json.dumps(error_result, indent=2)}\n")
            return error_result
    def on_error(self, ws, error):
        print(f"WebSocket error occurred: {error}")
    def on_close(self, ws, close_status_code, close_msg):
        print(f"WebSocket connection closed. Status code: {close_status_code}, Message: {close_msg}")
        if self.audio_sender:
            self.audio_sender.stop()
        self.audio_player.close()
    def run(self):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        self.ws = websocket.WebSocketApp(WEBSOCKET_URL,
                                         header=headers,
                                         on_open=self.on_open,
                                         on_message=self.on_message,
                                         on_error=self.on_error,
                                         on_close=self.on_close)
        wst = threading.Thread(target=self.ws.run_forever, daemon=True)
        wst.start()
        while not self.ws.sock or not self.ws.sock.connected:
            pass
        print("Listening and speaking to the assistant. Press Ctrl+C to exit.")
        while not interrupted:
            pass
        self.ws.close()
        if self.audio_sender:
            self.audio_sender.stop()
        self.audio_player.close()

def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set.")
        sys.exit(1)
    chat = ChatStreaming(api_key)
    chat.run()

if __name__ == "__main__":
    main()