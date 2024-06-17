
import re
import os
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('API_KEY')
client = OpenAI(api_key=api_key)
processing = False
responding = False

def process_input(toRead):
    try:
        with open(toRead, 'r', encoding='utf-8') as file:
            data = file.read().replace('\n', ' ')
    except UnicodeDecodeError:
        with open(toRead, 'r', encoding='latin-1') as file:
            data = file.read().replace('\n', ' ')
    finally:
        return data


def split_text(text):
    sentences = re.split(r'(\. )', text)  # Split on ". " but keep the delimiter
    sections, current_section = [], ''

    for i in range(0, len(sentences), 2):
        sentence = sentences[i]
        if i + 1 < len(sentences):  # Append the delimiter back to the sentence
            sentence += sentences[i + 1]

        if len(current_section) + len(sentence) > 4000:
            sections.append(current_section.strip())
            current_section = sentence
        else:
            current_section += sentence

    if current_section:
        sections.append(current_section.strip())

    return sections

def process_output(client, text_array):
    global processing, responding
    n = 0
    for s in text_array:
        try:
            speech_response = client.audio.speech.create(model="tts-1-hd", voice="onyx", input=s)
            if not speech_response or not speech_response.content:
                raise ValueError("Failed to generate speech response")

            output_audio_path = Path(f"./output/outputAudio{n}.mp3")
            n+=1

            # pygame.mixer.music.unload()

            with output_audio_path.open("wb") as out_file:
                out_file.write(speech_response.content)

            if output_audio_path.stat().st_size == 0:
                raise ValueError("Written audio file is empty")

            # pygame.mixer.music.load(str(output_audio_path))
            # pygame.mixer.music.play()
            # responding = True
            # while pygame.mixer.music.get_busy():
            #     time.sleep(0.1)
            
            # time.sleep(0.5)
            # responding = False
        except Exception as e:
            print(f"Error processing output: {e}")
        finally:
            processing = False

INPUT_FILENAME = 'input.txt'

big_string = process_input(INPUT_FILENAME)
split_text_array = split_text(big_string)
process_output(client, split_text_array)
