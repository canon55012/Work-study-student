import socket
import sys
import time


def wait(host: str, port: int, timeout: float, interval: float = 0.3) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = socket.socket()
        s.settimeout(0.5)
        try:
            s.connect((host, port))
            return True
        except Exception:
            time.sleep(interval)
        finally:
            s.close()
    return False


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    secs = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0
    sys.exit(0 if wait(host, port, secs) else 1)
