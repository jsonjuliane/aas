"""
Bench test for Biñan geofence and recipient routing — run: python -m src.routing_test
"""

from __future__ import annotations

from src import contacts
from src.routing import (
    area_label,
    classify_location,
    get_recipients,
    is_inside_binan,
    resolve_accident_barangay,
)


def _check(name: str, lat: float, lon: float, expect_inside: bool) -> None:
    inside = is_inside_binan(lat, lon)
    cls = classify_location(lat, lon)
    label = area_label(cls)
    ok = inside == expect_inside
    tag = "OK" if ok else "FAIL"
    print(f"[{tag}] {name}: ({lat}, {lon}) -> {label} (inside={inside})")
    if not ok:
        raise SystemExit(1)


def _check_recipients(
    name: str,
    lat: float | None,
    lon: float | None,
    home_barangay: str,
    *,
    min_count: int,
    must_include: list[str] | None = None,
    expect_accident: str | None = None,
) -> None:
    family = ["+639000000001"]
    out = get_recipients(
        lat,
        lon,
        family_phones=family,
        home_barangay=home_barangay,
    )
    phones = out["phones"]
    ok = len(phones) >= min_count
    if must_include:
        ok = ok and all(p in phones for p in must_include)
    if expect_accident is not None:
        ok = ok and out.get("accident_barangay") == expect_accident
    tag = "OK" if ok else "FAIL"
    print(
        f"[{tag}] Recipients {name}: count={len(phones)} phones={phones} "
        f"accident={out.get('accident_barangay')} notified={out.get('notified')}"
    )
    if not ok:
        raise SystemExit(1)


def main() -> int:
    _check("Biñan center", 14.34267, 121.08071, True)
    _check("Langkiwa", 14.2965, 121.0649, True)
    _check("Manila", 14.5905, 120.9800, False)
    cls = classify_location(None, None)
    print(f"[OK] No GPS: {area_label(cls)} (class={cls})")

    barangay_map, _ = contacts.load_barangay_contacts()
    zapote_rescuer = contacts.lookup_rescuer_phone("Zapote", barangay_map)
    langkiwa_rescuer = contacts.lookup_rescuer_phone("Langkiwa", barangay_map)

    accident, method = resolve_accident_barangay(14.2989841, 121.0597082)
    print(
        f"[{'OK' if accident == 'Langkiwa' else 'FAIL'}] "
        f"resolve_accident at Langkiwa -> {accident} ({method})"
    )
    if accident != "Langkiwa":
        raise SystemExit(1)

    _check_recipients(
        "inside Biñan, home Zapote, accident near Langkiwa",
        14.2989841,
        121.0597082,
        "Zapote",
        min_count=2,
        must_include=[zapote_rescuer],  # home + accident rescuer deduped when same number
        expect_accident="Langkiwa",
    )
    _check_recipients(
        "outside Biñan + Zapote home",
        14.5905,
        120.98,
        "Zapote",
        min_count=2,
        must_include=[zapote_rescuer],  # type: ignore[list-item]
        expect_accident=None,
    )
    _check_recipients(
        "no GPS + Zapote home",
        None,
        None,
        "Zapote",
        min_count=2,
        must_include=[zapote_rescuer],  # type: ignore[list-item]
        expect_accident=None,
    )
    _check_recipients(
        "unknown home barangay name",
        None,
        None,
        "Not A Real Barangay",
        min_count=1,
        expect_accident=None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
