from __future__ import annotations


def hm_to_min(s: str) -> int:
    h, m = s.split(":")[:2]
    return int(h) * 60 + int(m)


def min_to_hm(m: int) -> str:
    m = int(m)
    return f"{m // 60:02d}:{m % 60:02d}"


def iso_local_hm(iso: str) -> str:
    """'2022-08-03T17:02:00.000-05:00' -> '17:02' (the catalog stores local times with offsets)."""
    return iso[11:16]
