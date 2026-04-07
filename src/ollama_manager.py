"""Start and stop the Ollama server process."""
import logging
import subprocess
import time
import httpx

from .config import OLLAMA_HOST, OLLAMA_MODEL

log = logging.getLogger(__name__)

_ollama_proc = None


def start() -> None:
    global _ollama_proc
    # Check if already running
    try:
        httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        log.info("Ollama already running")
        return
    except Exception:
        pass

    log.info("Starting Ollama...")
    _ollama_proc = subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait until responsive
    for _ in range(30):
        time.sleep(1)
        try:
            httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
            log.info("Ollama is up")
            return
        except Exception:
            continue

    raise RuntimeError("Ollama did not start within 30 seconds")


def ensure_model() -> None:
    """Pull model if not already available locally."""
    resp = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=10)
    resp.raise_for_status()
    available = [m["name"] for m in resp.json().get("models", [])]
    if OLLAMA_MODEL not in available:
        log.info("Pulling model %s...", OLLAMA_MODEL)
        result = subprocess.run(["ollama", "pull", OLLAMA_MODEL], check=True)
        log.info("Model pulled: %s", result.returncode)


def stop() -> None:
    global _ollama_proc
    if _ollama_proc is not None:
        log.info("Stopping Ollama (pid=%d)", _ollama_proc.pid)
        _ollama_proc.terminate()
        _ollama_proc.wait(timeout=10)
        _ollama_proc = None
