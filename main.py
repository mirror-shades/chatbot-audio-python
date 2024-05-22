import pygame
import pyaudio
import wave
import threading
import math
import time
import os
from pathlib import Path
from openai import OpenAI
from pydub import AudioSegment
from pydub.utils import make_chunks
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('API_KEY')

# Initialize pygame and audio
pygame.init()
pygame.mixer.init()
py_audio = pyaudio.PyAudio()

# Screen settings
WIDTH, HEIGHT = 640, 480
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Audio Recorder")

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GREY = (128, 128, 128)

# Button settings
BUTTON_RADIUS = int(min(WIDTH, HEIGHT) / 4)
button_center = (WIDTH // 2, HEIGHT // 2)

# Audio settings
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024
WAVE_OUTPUT_FILENAME = "inputAudio.wav"

# Variables
frames = []
recording = False
processing = False
chat_history = []
responding = False
prompt = ("You are a chatbot named Mimesis. You are an audio chatbot, the user will be speaking to you, "
            "and your responses will be read aloud to the user. Try and come off personable rather than formal. Be very friendly. "
            "Try and keep chats as conversational as possible. If a question is complicated ask the user to use "
            "your (you being the Mimesis Chatbot) text chat feature. DO NOT USE "
            "LISTS. DO NOT MAKE A NUMBERED LIST UNLESS SPECIFICALLY ASKED.")

def add_to_history(role, content):
    chat_history.append({'role': role, 'content': content})

# Audio record function
def record_audio():
    global recording, frames
    stream = None
    try:
        stream = py_audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True,
                            frames_per_buffer=CHUNK)
        frames = []
        while recording:
            data = stream.read(CHUNK)
            frames.append(data)
    finally:
        if stream:
            stream.stop_stream()
            stream.close()

# Convert audio to string
def convert_audio_to_string(client):
    global chat_history
    try:
        with Path(WAVE_OUTPUT_FILENAME).open("rb") as audio_file:
            transcription = client.audio.transcriptions.create(model="whisper-1", file=audio_file)
        user_message = transcription.text
        add_to_history("user", user_message)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=chat_history
        )
        response_text = response.choices[0].message.content
        if not response_text:
            raise ValueError("No response text generated")
        add_to_history("assistant", response_text)
        return response_text
    except Exception as e:
        print(f"Error converting audio to string: {e}")
        return None

# Process output
def process_output(client, response_text):
    global processing, responding
    try:
        speech_response = client.audio.speech.create(model="tts-1-hd", voice="nova", input=response_text)
        if not speech_response or not speech_response.content:
            raise ValueError("Failed to generate speech response")

        output_audio_path = Path("./outputAudio.mp3")

        pygame.mixer.music.unload()

        with output_audio_path.open("wb") as out_file:
            out_file.write(speech_response.content)

        if output_audio_path.stat().st_size == 0:
            raise ValueError("Written audio file is empty")

        pygame.mixer.music.load(str(output_audio_path))
        pygame.mixer.music.play()
        responding = True
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        
        time.sleep(0.5)
        responding = False

    except Exception as e:
        print(f"Error processing output: {e}")
    finally:
        processing = False

# Run the entire process
def runProgram(client):
    with wave.open(WAVE_OUTPUT_FILENAME, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(py_audio.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

    response_text = convert_audio_to_string(client)
    if response_text:
        process_output(client, response_text)

def get_audio_frame_loudness(audio_segment):
    return audio_segment.dBFS

def get_background_color(db_avg_value):
    if db_avg_value == float('-inf'):
        db_avg_value = -60  # Assume silence as -60 dB
    else:
        db_avg_value = (db_avg_value + 60) / 60  # db_value ranges from -60 to 0
    color_scale = int(255 * db_avg_value)  # Map to 0-255 range
    color_scale = max(0, min(color_scale, 255))  # Ensure the value is within 0-255
    return (color_scale, color_scale, color_scale)  # RGB values will be the same for grey scale

# Smooth volume changes with a sliding window
smooth_window_size = 10
volume_window = []

def smooth_volume(db_value):
    volume_window.append(db_value)
    if len(volume_window) > smooth_window_size:
        volume_window.pop(0)
    return sum(volume_window) / len(volume_window)

# Main loop
running = True
button_pressed = False
client = OpenAI(api_key=api_key)
clock = pygame.time.Clock()
spinner_color = (255, 255, 255)  # White color
spinner_radius = 50
spinner_angle = 0
center = (WIDTH // 2, HEIGHT // 2)
frame_index = 0
chunks = []
total_frames = 0
add_to_history("system", prompt)


def update_spinner(spinner_angle, center, radius):
    end_pos = (
        center[0] + radius * math.cos(math.radians(spinner_angle)),
        center[1] - radius * math.sin(math.radians(spinner_angle))
    )
    ball_radius = 15  # Define ball radius
    pygame.draw.circle(screen, spinner_color, (int(end_pos[0]), int(end_pos[1])), ball_radius)

def update_background(chunks, frame_index):
    if frame_index < total_frames:
        frame_audio = chunks[frame_index]
        db_value = get_audio_frame_loudness(frame_audio)
        smoothed_db_value = smooth_volume(db_value)
        background_color = get_background_color(smoothed_db_value)
        screen.fill(background_color)
        return frame_index + 1
    return frame_index

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
            recording = False
        elif event.type == pygame.MOUSEBUTTONDOWN and not processing and not responding:
            pos = pygame.mouse.get_pos()
            if (pos[0] - button_center[0]) ** 2 + (pos[1] - button_center[1]) ** 2 <= BUTTON_RADIUS ** 2:
                if not recording:
                    recording = True
                    threading.Thread(target=record_audio).start()
                button_pressed = True
        elif event.type == pygame.MOUSEBUTTONUP:
            if recording:
                recording = False
                if frames:
                    processing = True
                    threading.Thread(target=runProgram, args=(client,)).start()
            button_pressed = False

    screen.fill(BLACK)

    if processing and not responding:
        update_spinner(spinner_angle, center, spinner_radius)
        spinner_angle = (spinner_angle - 7) % 360

    if responding:
        audio_file = "outputAudio.mp3"
        if not chunks:
            audio_segment = AudioSegment.from_mp3(audio_file)
            frame_duration = 1000 // 60
            chunks = make_chunks(audio_segment, frame_duration)
            total_frames = len(chunks)
        frame_index = update_background(chunks, frame_index)

    if not processing and not responding:
        button_color = GREY if button_pressed else WHITE
        pygame.draw.circle(screen, button_color, button_center, BUTTON_RADIUS)

    pygame.display.flip()
    clock.tick(60)

# Cleanup
pygame.quit()
py_audio.terminate()