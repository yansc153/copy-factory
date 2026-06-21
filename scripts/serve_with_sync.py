from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Config
from app.sync import run_sync
from app.web import Handler


def sync_once() -> None:
    result = run_sync(Config())
    print(
        f"sync {result.batch} fetched={result.fetched} inserted={result.inserted} "
        f"generated={result.generated} skipped={result.skipped} errors={len(result.errors)}",
        flush=True,
    )


def sync_loop() -> None:
    interval = max(60, int(os.getenv("COPY_FACTORY_SYNC_INTERVAL_SECONDS", "1800")))
    if os.getenv("COPY_FACTORY_SYNC_ON_START", "1") != "0":
        try:
            sync_once()
        except Exception as exc:
            print(f"sync startup failed: {exc}", flush=True)
    while True:
        time.sleep(interval)
        try:
            sync_once()
        except Exception as exc:
            print(f"sync failed: {exc}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    Handler.config.validate_for_web()
    threading.Thread(target=sync_loop, daemon=True).start()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Copy Factory running at http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Copy Factory stopping", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
