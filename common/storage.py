import contextlib
import json
import os
import time

_LOCK_TIMEOUT = 10.0
_LOCK_POLL = 0.05
_LOCK_STALE = 30.0


@contextlib.contextmanager
def file_lock(path):
    lock_path = str(path) + ".lock"
    parent = os.path.dirname(lock_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    fd = None
    deadline = time.time() + _LOCK_TIMEOUT
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock_path) > _LOCK_STALE:
                    os.remove(lock_path)
                    continue
            except FileNotFoundError:
                continue
            if time.time() > deadline:
                break
            time.sleep(_LOCK_POLL)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            os.remove(lock_path)


def append_jsonl(path, obj):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False)
    with file_lock(path):
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def read_jsonl(path, limit=None):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows[-limit:] if limit else rows
