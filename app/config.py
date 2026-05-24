import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODELS_DIR  = os.path.join(BASE_DIR, "models")
TEMP_DIR    = os.path.join(BASE_DIR, "temp")
LOG_FILE    = os.path.join(BASE_DIR, "speakeasy.log")
TEMP_WAV    = os.path.join(TEMP_DIR, "recording.wav")

MODEL_SIZE  = "large-v3-turbo"
SAMPLE_RATE = 16000
CHANNELS    = 1
