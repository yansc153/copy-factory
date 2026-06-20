#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Config
from app.sync import run_sync


if __name__ == "__main__":
    result = run_sync(Config())
    print(
        f"batch={result.batch} fetched={result.fetched} inserted={result.inserted} "
        f"duplicates={result.duplicates} generated={result.generated} errors={len(result.errors)}"
    )
    for error in result.errors:
        print(f"error: {error}")
