import ctypes
import glob
import logging
import os
import site

log = logging.getLogger(__name__)


def _preload_cuda_libs():
    """ctranslate2 dlopens libcublas.so.12 / libcudnn.so.9 by SONAME, but the
    nvidia-cublas-cu12 / nvidia-cudnn-cu12 wheels drop them under
    site-packages/nvidia/{cublas,cudnn}/lib/, which the linker doesn't search.
    Preload them with RTLD_GLOBAL so ctranslate2 finds them already mapped."""
    soname_dirs = []
    for sp in site.getsitepackages() + [site.getusersitepackages()]:
        soname_dirs.append(os.path.join(sp, "nvidia"))
    seen = set()
    for base in soname_dirs:
        if not os.path.isdir(base) or base in seen:
            continue
        seen.add(base)
        for lib in glob.glob(os.path.join(base, "*", "lib", "lib*.so.*")):
            try:
                ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
            except OSError as ex:
                log.debug("preload skipped %s: %s", lib, ex)


_preload_cuda_libs()

from faster_whisper import WhisperModel  # noqa: E402

from config import MODEL_SIZE, MODELS_DIR  # noqa: E402


class Transcriber:
    def __init__(self):
        self._model = None

    def load(self):
        log.info("Loading Whisper model: %s on CUDA", MODEL_SIZE)
        self._model = WhisperModel(
            MODEL_SIZE, device="cuda", compute_type="float16",
            download_root=MODELS_DIR,
        )
        log.info("Model loaded on GPU")

    def transcribe(self, wav_path):
        if not self._model:
            log.error("Model not loaded")
            return ""
        log.info("Transcription started")
        try:
            segments, _info = self._model.transcribe(wav_path, beam_size=5, language="en")
            text = " ".join(seg.text.strip() for seg in segments).strip()
            log.info("Transcription completed: %r", text)
            return text
        except Exception as e:
            log.error("Transcription failed: %s", e)
            return ""
