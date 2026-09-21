"""Optional same-process-tree demo server, also useful in isolated sandboxes."""
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.request import urlopen


@contextmanager
def local_server(enabled=True):
    if not enabled:
        yield
        return
    process = subprocess.Popen([sys.executable, "-m", "mock_bank"], cwd=Path(__file__).resolve().parents[1],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("Mock server failed to start; port 8000 may be occupied. Omit --start-app when already running.")
            try:
                with urlopen("http://127.0.0.1:8000/", timeout=0.2) as response:
                    if "LedgerDesk" in response.read().decode():
                        break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("Mock server did not become ready")
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
