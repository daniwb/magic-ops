"""Disposable producer read cache. Source files and live job state stay authoritative."""
import hashlib
import json
import os
import sqlite3
from pathlib import Path


class ProducerCache:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS cache (namespace TEXT, key TEXT, stamp TEXT, value TEXT, PRIMARY KEY(namespace,key))')

    def get(self, namespace, key, stamp):
        row = self.db.execute('SELECT value FROM cache WHERE namespace=? AND key=? AND stamp=?',
                              (namespace, str(key), str(stamp))).fetchone()
        return (True, json.loads(row[0])) if row else (False, None)

    def put(self, namespace, key, stamp, value):
        self.db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?,?)',
                        (namespace, str(key), str(stamp), json.dumps(value, separators=(',', ':'))))

    def file(self, namespace, path, project=lambda value: value):
        path = Path(path)
        stat = path.stat()
        stamp = '%s:%s:%s:%s' % (stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
        found, value = self.get(namespace, os.path.abspath(path), stamp)
        if found:
            return value
        try:
            raw = json.loads(path.read_text())
        except OSError:
            return None
        except ValueError:
            # Legacy raw logs may be JSONL despite their .json extension.
            # Retry when the source changes, including a partial file completing.
            self.put(namespace, os.path.abspath(path), stamp, None)
            return None
        value = project(raw)
        self.put(namespace, os.path.abspath(path), stamp, value)
        return value

    def files(self, namespace, directory, project):
        """Bulk-load a compact directory index; stat every source before reuse."""
        prefix = os.path.abspath(directory) + os.sep
        known = {key: (stamp, value) for key, stamp, value in self.db.execute(
            'SELECT key,stamp,value FROM cache WHERE namespace=?', (namespace,))
            if key.startswith(prefix) and os.sep not in key[len(prefix):]}
        present, result = set(), []
        try:
            with os.scandir(directory) as listing:
                entries = sorted((entry for entry in listing if entry.name.endswith('.json')), key=lambda entry: entry.name)
        except FileNotFoundError:
            entries = []
        for entry in entries:
            path = Path(entry.path)
            key = os.path.abspath(path)
            present.add(key)
            try:
                stat = entry.stat()
            except FileNotFoundError:
                continue
            stamp = '%s:%s:%s:%s' % (stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
            old = known.get(key)
            if old and old[0] == stamp:
                value = json.loads(old[1])
            else:
                value = self.file(namespace, path, project)
            result.append((path, value or {}))
        self.db.executemany('DELETE FROM cache WHERE namespace=? AND key=?',
                            [(namespace, key) for key in known.keys() - present])
        return result

    def checkpoint(self):
        self.db.commit()

    def close(self):
        self.db.commit()
        self.db.close()


def receipt_demand(value):
    if not isinstance(value, dict):
        return None
    if not value.get('capability_demand') and value.get('outcome') != 'invalid_capability_demand':
        return None
    return {key: value[key] for key in ('ticket', 'outcome', 'capability_demand', 'raw_artifacts') if key in value}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
