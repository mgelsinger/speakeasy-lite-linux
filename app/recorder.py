import logging
import wave

import numpy as np
import sounddevice as sd

from config import CHANNELS, SAMPLE_RATE, TEMP_WAV

log = logging.getLogger(__name__)


class Recorder:
    def __init__(self):
        self.is_recording = False
        self._frames = []
        self._stream = None

    def start(self):
        if self.is_recording:
            return
        log.info("Recording started")
        self._frames = []
        self.is_recording = True
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata, frames, time, status):
        if status:
            log.warning("Audio status: %s", status)
        self._frames.append(indata.copy())

    def stop(self):
        if not self.is_recording:
            return None
        self.is_recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        log.info("Recording stopped")

        if not self._frames:
            log.warning("No audio captured")
            return None

        audio = np.concatenate(self._frames, axis=0)
        self._save_wav(audio)
        return TEMP_WAV

    def _save_wav(self, audio):
        with wave.open(TEMP_WAV, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        log.info("WAV saved: %s", TEMP_WAV)
