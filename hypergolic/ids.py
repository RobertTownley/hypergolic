"""Short, sortable, alphanumeric IDs.

Generates 12-character IDs using Crockford Base32 (`0-9A-Z` minus I, L, O, U).
Layout: 42 bits of millisecond timestamp (good through ~year 2109) followed by
18 bits of randomness. Total 60 bits = 12 base32 chars.

Lexicographic order matches chronological order, giving UUIDv7-like sortability
in one third of the characters. Within a single millisecond, later IDs reuse
the previous random value incremented by one (ULID's monotonic scheme): a
burst of any realistic size is guaranteed unique in-process, still sorted in
generation order, and only 18 random bits are needed. A different process
colliding requires the same ms *and* the same 18-bit draw. Generation-order
sorting assumes the wall clock doesn't step backward mid-burst (NTP).
"""
from __future__ import annotations

import secrets
import threading
import time

# Crockford Base32 alphabet: 0-9 then A-Z excluding I, L, O, U.
# Sorts lexicographically in the same order as numerically.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

ID_LENGTH = 12
_TIMESTAMP_BITS = 42
_RANDOM_BITS = ID_LENGTH * 5 - _TIMESTAMP_BITS  # 18
_RANDOM_MAX = 1 << _RANDOM_BITS
_TIMESTAMP_MAX = 1 << _TIMESTAMP_BITS


def _encode(value: int, length: int) -> str:
    chars = ["0"] * length
    for i in range(length - 1, -1, -1):
        chars[i] = _ALPHABET[value & 0x1F]
        value >>= 5
    return "".join(chars)


_state_lock = threading.Lock()
_last_ts = -1
_last_rand = 0


def new_id(now_ms: int | None = None) -> str:
    """Return a new 12-char Crockford Base32 sortable ID.

    `now_ms` lets tests inject a deterministic timestamp.
    """
    global _last_ts, _last_rand
    ts = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    ts &= _TIMESTAMP_MAX - 1  # defensive; real timestamps won't exceed 42 bits until ~2109
    with _state_lock:
        if now_ms is None and ts < _last_ts:
            # The wall clock lags _last_ts after a borrow (below) or a backward
            # step; resetting to it would break sort order. Injected timestamps
            # stay authoritative so tests are deterministic.
            ts = _last_ts
        if ts == _last_ts:
            _last_rand += 1
            if _last_rand >= _RANDOM_MAX:
                # 262k IDs in one ms; borrow the next ms rather than wrap.
                _last_ts = ts = ts + 1
                _last_rand = secrets.randbelow(_RANDOM_MAX)
        else:
            _last_ts = ts
            _last_rand = secrets.randbelow(_RANDOM_MAX)
        rand = _last_rand
    combined = (ts << _RANDOM_BITS) | rand
    return _encode(combined, ID_LENGTH)
