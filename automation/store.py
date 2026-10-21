"""Settings, the encrypted token store, and the record of what has been posted."""

import json
import os
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "automation"
CONFIG_FILE = HERE / "config.json"
TOKENS_FILE = HERE / "tokens.json"
LOG_FILE = HERE / "post-log.json"
KEY_FILE = HERE / ".tokens-key"


def read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_config():
    return read_json(CONFIG_FILE, None)


def create_key():
    """Writes a fresh encryption key to KEY_FILE. Returns False if one is already there."""
    if KEY_FILE.exists():
        return False
    KEY_FILE.write_bytes(Fernet.generate_key())
    return True


class Tokens:
    """Access tokens, encrypted with TOKENS_KEY so tokens.json can sit in a public repo.

    Only the token itself is encrypted. Account names, IDs and dates stay readable.
    """

    def __init__(self):
        self.data = read_json(TOKENS_FILE, {})
        self._fernet = None

    def _cipher(self):
        if self._fernet is None:
            key = os.environ.get("TOKENS_KEY", "").strip()
            if not key and KEY_FILE.exists():
                key = KEY_FILE.read_text(encoding="ascii").strip()
            if not key:
                raise SystemExit(
                    "No encryption key. On GitHub, add the TOKENS_KEY secret. "
                    "Locally, run `python automation/poster.py init-key`."
                )
            self._fernet = Fernet(key.encode())
        return self._fernet

    def get(self, app, platform):
        record = self.data.get(app, {}).get(platform)
        if not record:
            return None
        try:
            token = self._cipher().decrypt(record["token"].encode()).decode()
        except InvalidToken:
            raise SystemExit(
                f"Cannot decrypt the {platform} token for {app}: TOKENS_KEY is not the key it was saved with."
            )
        return {**record, "token": token}

    def put(self, app, platform, record):
        encrypted = self._cipher().encrypt(record["token"].encode()).decode()
        self.data.setdefault(app, {})[platform] = {**record, "token": encrypted}

    def save(self):
        write_json(TOKENS_FILE, self.data)


class PostLog:
    """One entry per automated post: when it went out and where it lives on each platform."""

    def __init__(self):
        self.entries = read_json(LOG_FILE, [])

    def find(self, app, post_name):
        matches = [e for e in self.entries if e["app"] == app and e["post"] == post_name]
        return matches[-1] if matches else None

    def last_day(self, app, tz):
        """The posting day of the app's latest post. A late post that went out after midnight counts
        for the day it was scheduled, so it doesn't push the next post back a cycle."""
        days = [
            datetime.fromisoformat(e.get("slot") or e["posted_at"]).astimezone(tz).date()
            for e in self.entries
            if e["app"] == app and e.get("posted_at")
        ]
        return max(days, default=None)

    def add(self, entry):
        self.entries.append(entry)

    def save(self):
        write_json(LOG_FILE, self.entries)
