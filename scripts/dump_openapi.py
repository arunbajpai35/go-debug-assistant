"""dump the live fastapi openapi spec to stdout.

usage:
    python scripts/dump_openapi.py > openapi.json

CI runs this and diffs against the committed openapi.json so the spec stays current."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

# allow `python scripts/dump_openapi.py` from the repo root without setting PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# avoid touching real postgres at import time
with patch("backend.db.init_pool"), patch("backend.db.close_pool"):
    from backend.api import app

    print(json.dumps(app.openapi(), indent=2, sort_keys=True))
