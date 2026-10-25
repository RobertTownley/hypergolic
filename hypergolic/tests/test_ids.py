"""Tests for `hypergolic.ids`."""
from __future__ import annotations

import re
import time

from hypergolic.ids import (
    ID_LENGTH,
    _ALPHABET,
    new_id,
)
import hypergolic.ids as ids_mod

_ALPHABET_RE = re.compile(f"^[{_ALPHABET}]+$")


def test_length_is_twelve() -> None:
    assert len(new_id()) == ID_LENGTH == 12


def test_only_uses_crockford_alphabet() -> None:
    # Generate a batch to cover a wide range of characters.
    for _ in range(200):
        value = new_id()
        assert _ALPHABET_RE.match(value), value
        # Crockford omits these ambiguous chars.
        for forbidden in "ILOU":
            assert forbidden not in value


def test_ids_are_unique_in_a_tight_burst() -> None:
    # The monotonic same-ms scheme guarantees in-process uniqueness: no
    # birthday math, no flaky margin.
    ids = [new_id() for _ in range(5000)]
    assert len(set(ids)) == 5000
    assert ids == sorted(ids)


def test_borrowed_ms_keeps_sort_order() -> None:
    # A random draw near the max overflows mid-burst and borrows the next ms.
    # IDs generated while the wall clock still lags the borrowed ms must not
    # reset the state backward (this fired ~2% of 5000-id bursts). A future
    # _last_ts makes the wall clock lag deterministically.

    with ids_mod._state_lock:
        saved = (ids_mod._last_ts, ids_mod._last_rand)
        ids_mod._last_ts = 2_000_000_000_000  # 2033; real clock always lags
        ids_mod._last_rand = ids_mod._RANDOM_MAX - 2

    try:
        ids = [ids_mod.new_id() for _ in range(50)]
    finally:
        with ids_mod._state_lock:
            ids_mod._last_ts, ids_mod._last_rand = saved
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_injected_timestamp_is_respected() -> None:
    ts = 1_700_000_000_000  # 2023-11-14T22:13:20Z, well within 42 bits
    ids = [new_id(now_ms=ts) for _ in range(20)]
    # 42 timestamp bits span 8 full chars (40 bits) plus 2 bits of char index 8,
    # which mixes with random bits. Only the first 8 chars are guaranteed stable.
    prefixes = {value[:8] for value in ids}
    assert len(prefixes) == 1


def test_lexicographic_order_matches_time_order() -> None:
    earlier = new_id(now_ms=1_000_000_000_000)
    middle = new_id(now_ms=1_500_000_000_000)
    later = new_id(now_ms=2_000_000_000_000)
    assert earlier < middle < later


def test_monotonic_across_real_time() -> None:
    a = new_id()
    time.sleep(0.005)  # 5ms: larger than 1ms tick, smaller than test overhead budget
    b = new_id()
    assert a < b


def test_sort_stable_across_many_timestamps() -> None:
    # Strictly increasing timestamps should yield strictly increasing IDs
    # regardless of random suffix.
    timestamps = [1_700_000_000_000 + i * 1000 for i in range(50)]
    ids = [new_id(now_ms=ts) for ts in timestamps]
    assert ids == sorted(ids)
