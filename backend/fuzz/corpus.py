"""The persistent corpus — what makes a 24-hour campaign worth more than 24 one-hour campaigns.

Inputs are stored content-addressed (sha1 of the bytes) so a re-run never duplicates an entry and
two machines can merge corpora by copying files. That is the same scheme AFL and libFuzzer use.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


class Corpus:
    """A directory of input files, addressed by content hash.

    Kept deliberately dumb: no metadata sidecar, no index. The filename IS the identity, so the
    corpus survives being copied, merged, or partially deleted, and `git status` shows exactly
    which inputs a campaign added.
    """

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()
        self._entries: list[bytes] = []
        self._load()

    def _load(self) -> None:
        for path in sorted(self.dir.iterdir()):
            if path.is_file():
                data = path.read_bytes()
                digest = _digest(data)
                if digest not in self._seen:
                    self._seen.add(digest)
                    self._entries.append(data)

    def add(self, data: bytes) -> bool:
        """Store `data` if it is new. Returns True if it was actually added."""
        digest = _digest(data)
        if digest in self._seen:
            return False
        self._seen.add(digest)
        self._entries.append(data)
        (self.dir / digest).write_bytes(data)
        return True

    def seed(self, entries: list[bytes]) -> None:
        """Prime an empty corpus. A no-op once anything is stored, so a campaign that has already
        learned something is never dragged back to the starting set."""
        for data in entries:
            self.add(data)

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)

    @property
    def entries(self) -> list[bytes]:
        return self._entries


def _digest(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()
