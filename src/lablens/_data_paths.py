"""Locate the bundled `data/` directory regardless of install layout.

The package can run in three modes:

  1. **Editable install** (`pip install -e .` for dev) — `__file__` lives
     in `<repo>/src/lablens/...` so `parents[2]` resolves to the repo root.
  2. **Wheel/site-packages install** (`pip install .` in Docker) —
     `__file__` lives in `/usr/local/lib/python3.11/site-packages/lablens/...`
     and walking up parents lands inside site-packages, NOT the repo. The
     `data/` directory is not part of the wheel either, so we must look
     elsewhere on disk.
  3. **Tests / scripts** — usually run from the repo root with `data/`
     under CWD.

Resolution order (first existing wins):

    $LABLENS_DATA_DIR  →  /app/data  →  <repo>/data (editable install)
                       →  CWD/data

Setting `LABLENS_DATA_DIR=/app/data` in `docker-compose.prod.yml` makes
this deterministic in production; the other candidates are safety nets.

Result is cached for the process lifetime.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def data_root() -> Path:
    """Return the resolved `data/` directory.

    Raises:
        FileNotFoundError: if no candidate exists (misconfigured deploy).
    """
    candidates: list[Path] = []

    env = os.environ.get("LABLENS_DATA_DIR")
    if env:
        candidates.append(Path(env))

    candidates.extend(
        [
            Path("/app/data"),  # Docker prod layout
            # Editable install: src/lablens/_data_paths.py → parents[2] = <repo>
            Path(__file__).resolve().parents[2] / "data",
            Path.cwd() / "data",  # last resort
        ]
    )

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate

    tried = ", ".join(str(c) for c in candidates)
    raise FileNotFoundError(
        f"Could not locate lablens data/ directory. Tried: {tried}"
    )


def data_path(*parts: str) -> Path:
    """Return `data_root() / parts...` — convenience join."""
    return data_root().joinpath(*parts)
