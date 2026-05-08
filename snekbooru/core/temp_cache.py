import os
import shutil
import tempfile
import time


def snekbooru_temp_root():
    root = os.path.join(tempfile.gettempdir(), "Snekbooru")
    os.makedirs(root, exist_ok=True)
    return root


def snekbooru_temp_dir(*parts):
    path = os.path.join(snekbooru_temp_root(), *parts)
    os.makedirs(path, exist_ok=True)
    return path


def cleanup_snekbooru_temp(ttl_seconds):
    if ttl_seconds is None:
        return 0
    ttl_seconds = int(ttl_seconds)
    if ttl_seconds <= 0:
        return 0

    root = snekbooru_temp_root()
    now = time.time()
    removed = 0

    for base, dirs, files in os.walk(root, topdown=False):
        for name in files:
            path = os.path.join(base, name)
            try:
                age = now - os.path.getmtime(path)
                if age >= ttl_seconds:
                    os.remove(path)
                    removed += 1
            except Exception:
                pass

        for name in dirs:
            dpath = os.path.join(base, name)
            try:
                if not os.listdir(dpath):
                    os.rmdir(dpath)
            except Exception:
                pass

    try:
        if not os.listdir(root):
            os.makedirs(root, exist_ok=True)
    except Exception:
        pass

    return removed


def purge_snekbooru_temp():
    root = snekbooru_temp_root()
    try:
        shutil.rmtree(root, ignore_errors=True)
    except Exception:
        pass
    os.makedirs(root, exist_ok=True)
