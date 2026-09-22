"""Publish complete immutable receipts without exposing partial JSON to readers."""
import json
import os
from pathlib import Path
import tempfile


def write_receipt(path, value):
    path = Path(path)
    payload = json.dumps(value, indent=2, sort_keys=True) + '\n'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=path.parent, prefix='.' + path.name + '-',
                                         suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        # A same-filesystem hard link publishes the entire file atomically and
        # refuses to overwrite an existing immutable receipt on a name collision.
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
