#!/usr/bin/env python3
"""One WAV of speech with Kokoro (kokoro-onnx), free and local, on CPU: the default voice off the Mac.

usage: uv run --python 3.12 --with kokoro-onnx==0.6.1 --with soundfile==0.13.1 kokoro_say.py
           --text "Words." --out voice.wav [--voice af_heart] [--speed 1.0] [--cache DIR]

say.py runs this through uv, so the founder installs nothing by hand. The model (about 330 MB) and the voice
file download once into the cache folder (default ~/.cache/onca/kokoro) and are reused. Each file must match its
size and sha256 (FILES) before it is used; a bad download or a bad cached file is deleted. Kokoro is Apache-2.0.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import os
import sys
import urllib.request
from pathlib import Path
from typing import Optional

BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
TIMEOUT = 60  # seconds per read
CHUNK = 1 << 20
# name -> (size in bytes, sha256) of the release model-files-v1.0
FILES = {
    "kokoro-v1.0.onnx": (325532387, "7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5"),
    "voices-v1.0.bin": (28214398, "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"),
}


class DownloadError(Exception):
    """A model file could not be downloaded whole and unchanged."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _marker(target: Path) -> Path:
    return target.with_name(target.name + ".sha256")


def _cached(target: Path, size: int, sha: str) -> bool:
    """True when ``target`` is the expected file (its marker says so, or it is hashed once); a bad one is deleted."""
    marker = _marker(target)
    if not target.is_file():
        marker.unlink(missing_ok=True)  # a marker never outlives its file
        return False
    if target.stat().st_size == size:
        if marker.is_file() and marker.read_text(encoding="utf-8").strip() == sha:
            return True
        if sha256_file(target) == sha:
            marker.write_text(sha + "\n", encoding="utf-8")
            print(f"kokoro_say: verified {target.name} in the cache", file=sys.stderr)
            return True
    print(f"kokoro_say: {target.name} in the cache does not match its checksum, replacing it", file=sys.stderr)
    target.unlink()
    marker.unlink(missing_ok=True)
    return False


def _download(target: Path, size: int, sha: str, opener, timeout: float) -> None:
    """Stream ``target``'s file into ``<name>.part`` while hashing; move it into place only on a size and sha256 match."""
    name = target.name
    print(f"kokoro_say: downloading {name} once into {target.parent}", file=sys.stderr)
    part = target.with_name(name + ".part")
    digest, got = hashlib.sha256(), 0
    try:
        with opener(BASE + name, timeout=timeout) as response, open(part, "wb") as out:
            while got <= size:
                block = response.read(CHUNK)
                if not block:
                    break
                got += len(block)
                digest.update(block)
                out.write(block)
        if got != size or digest.hexdigest() != sha:
            raise DownloadError(f"{name} failed its checksum ({got} bytes, expected {size}); nothing was kept")
        os.replace(part, target)
    except (OSError, http.client.HTTPException) as error:  # a timeout, a URL error, a body cut short
        raise DownloadError(f"downloading {name} failed ({error}); nothing was kept") from error
    finally:
        part.unlink(missing_ok=True)  # gone already after the move
    _marker(target).write_text(sha + "\n", encoding="utf-8")
    print(f"kokoro_say: verified {name}", file=sys.stderr)


def fetch(cache: Path, opener=urllib.request.urlopen, files: Optional[dict] = None, timeout: float = TIMEOUT) -> tuple:
    """The paths of ``files`` (default FILES) in ``cache``, each checked by size and sha256 and downloaded when missing
    or bad. DownloadError when a download fails or does not match; no bad file and no ``.part`` file is left."""
    files = FILES if files is None else files
    cache.mkdir(parents=True, exist_ok=True)
    for name, (size, sha) in files.items():
        target = cache / name
        if not _cached(target, size, sha):
            _download(target, size, sha, opener, timeout)
    return tuple(cache / name for name in files)


def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--text", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--voice", default="af_heart")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache" / "onca" / "kokoro")
    args = parser.parse_args(argv)
    try:
        model, voices = fetch(args.cache)
    except DownloadError as error:
        print(f"kokoro_say: {error}", file=sys.stderr)
        sys.exit(1)
    import soundfile  # noqa: E402  (heavy imports only here: the script is also read by tests)
    from kokoro_onnx import Kokoro  # noqa: E402

    samples, rate = Kokoro(str(model), str(voices)).create(args.text, voice=args.voice, speed=args.speed, lang="en-us")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(str(args.out), samples, rate)
    print(f"kokoro_say: {len(args.text)} characters -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
