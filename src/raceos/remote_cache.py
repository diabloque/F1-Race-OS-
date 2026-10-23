"""A bounded, compressed HTTP cache. Only this directory is eligible for eviction."""

from __future__ import annotations
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
from threading import RLock
import time
import uuid
import requests
import truststore
from raceos.data import DataError


class RemoteUnavailable(DataError):
    pass


class RemoteMissing(RemoteUnavailable):
    pass


def download_json(url):
    # Windows/system certificates; TLS verification stays enabled.
    truststore.inject_into_ssl()
    try:
        with requests.get(url, timeout=(5, 15), stream=True) as response:
            if response.status_code == 404:
                raise RemoteMissing("This prepared data file is not published.")
            response.raise_for_status()
            payload = bytearray()
            for chunk in response.iter_content(65536):
                payload.extend(chunk)
                if len(payload) > 20 * 1024 * 1024:
                    raise RemoteUnavailable(
                        "The remote file exceeds the per-file limit."
                    )
        return json.loads(payload)
    except (requests.RequestException, ValueError) as error:
        raise RemoteUnavailable(
            "The remote data source could not be reached. Try again."
        ) from error


class RemoteCache:
    def __init__(self, directory, *, max_bytes=200 * 1024 * 1024, fetch=download_json):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_bytes, self.fetch = max_bytes, fetch
        self.lock = RLock()
        self.key_locks = [RLock() for _ in range(64)]
        self.memory = OrderedDict()
        self.pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="raceos-data")
        self.pending = set()
        self.downloads = 0
        with self.lock:
            self._evict()

    def get(self, key, urls, *, ttl=86400):
        digest = hashlib.sha256(key.encode()).hexdigest()
        path = self.directory / (digest + ".json.gz")
        # Stripe locks prevent duplicate downloads without retaining unbounded lock objects.
        with self.key_locks[int(digest[:4], 16) % len(self.key_locks)]:
            now = time.time()
            with self.lock:
                cached = self.memory.get(key)
                if cached and now - cached[0] < ttl:
                    self.memory.move_to_end(key)
                    if isinstance(cached[1], RemoteMissing):
                        raise cached[1]
                    return cached[1]
                if path.exists() and now - path.stat().st_mtime < ttl:
                    try:
                        value = json.loads(gzip.decompress(path.read_bytes()))
                    except (ValueError, OSError, EOFError):
                        path.unlink(missing_ok=True)
                    else:
                        self._remember(key, now, value)
                        return value
            failures = []
            for url in urls:
                try:
                    value = self.fetch(url)
                    break
                except RemoteUnavailable as error:
                    failures.append(error)
            else:
                if failures and all(
                    isinstance(error, RemoteMissing) for error in failures
                ):
                    error = RemoteMissing(
                        "This lap or session has no published prepared data."
                    )
                    with self.lock:
                        self._remember(key, now - ttl + 60, error)
                    raise error
                raise RemoteUnavailable(
                    "TracingInsights is temporarily unavailable. Try again."
                )
            encoded = gzip.compress(
                json.dumps(value, allow_nan=False, separators=(",", ":")).encode()
            )
            with self.lock:
                self.downloads += 1
                if len(encoded) <= self.max_bytes:
                    temporary = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
                    try:
                        temporary.write_bytes(encoded)
                        temporary.replace(path)
                        self._evict()
                    finally:
                        temporary.unlink(missing_ok=True)
                self._remember(key, now, value)
            return value

    def _remember(self, key, now, value):
        self.memory[key] = (now, value)
        self.memory.move_to_end(key)
        while len(self.memory) > 48:
            self.memory.popitem(last=False)

    def _evict(self):
        files = sorted(
            self.directory.glob("*.json.gz"), key=lambda p: p.stat().st_mtime
        )
        total = sum(path.stat().st_size for path in files)
        for path in files:
            if total <= self.max_bytes:
                break
            total -= path.stat().st_size
            path.unlink(missing_ok=True)

    def prefetch(self, key, urls):
        with self.lock:
            if key in self.pending or key in self.memory:
                return
            self.pending.add(key)

        def work():
            try:
                self.get(key, urls)
            except RemoteUnavailable:
                pass  # The next foreground request still reports a real failure.
            finally:
                with self.lock:
                    self.pending.discard(key)

        self.pool.submit(work)

    def info(self):
        with self.lock:
            paths = list(self.directory.glob("*.json.gz"))
            return {
                "used_bytes": sum(p.stat().st_size for p in paths),
                "limit_bytes": self.max_bytes,
                "files": len(paths),
                "downloads_this_run": self.downloads,
                "directory": str(self.directory),
            }

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)
