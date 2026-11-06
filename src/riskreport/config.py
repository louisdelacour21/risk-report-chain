import hashlib
from pathlib import Path

import tomllib

DEFAULT = Path(__file__).resolve().parents[2] / "config" / "default.toml"


def load(path=DEFAULT):
    """Returns (config dict, sha256 of the file bytes) so the journal can prove which parameters produced a run."""
    raw = Path(path).read_bytes()
    return tomllib.loads(raw.decode()), hashlib.sha256(raw).hexdigest()
