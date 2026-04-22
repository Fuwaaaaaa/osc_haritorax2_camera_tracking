"""Scan tool for nearby BLE devices — helps users discover HaritoraX2 peripherals.

Usage:
    python -m osc_tracking.tools.ble_scan [--timeout 10] [--all]

By default only devices whose advertised local name starts with
``HaritoraX2-`` are printed. Pass ``--all`` to see every nearby device
(useful if the tracker kit advertises under a different prefix).

Output is machine-friendly: one line per device, ``<local_name>\\t<address>``.
Copy the resulting local names into your ``config/default.json`` under
``ble_local_name_to_bone`` to wire them up as specific bones.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from ..ble_receiver import DEFAULT_NAME_PREFIX


async def _scan(timeout: float, show_all: bool) -> int:
    try:
        from bleak import BleakScanner
    except ImportError:
        print(
            "ERROR: bleak is not installed. Install with `pip install bleak` "
            "or `pip install -e .`.",
            file=sys.stderr,
        )
        return 2

    print(f"Scanning for {timeout:.0f} seconds...", file=sys.stderr)
    try:
        devices = await BleakScanner.discover(timeout=timeout)
    except Exception as exc:
        print(f"ERROR: BLE scan failed: {exc}", file=sys.stderr)
        return 1

    seen = 0
    for d in devices:
        name = getattr(d, "name", None) or ""
        if not show_all and not name.startswith(DEFAULT_NAME_PREFIX):
            continue
        print(f"{name or '(no name)'}\t{d.address}")
        seen += 1

    if seen == 0:
        hint = "" if show_all else f" (filter: name starts with '{DEFAULT_NAME_PREFIX}')"
        print(f"No devices found{hint}. Try --all to list everything nearby.", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List nearby BLE devices (HaritoraX2 filter by default)."
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="Scan duration in seconds")
    parser.add_argument("--all", action="store_true", help="Show every device, not just HaritoraX2")
    args = parser.parse_args()

    rc = asyncio.run(_scan(args.timeout, args.all))
    sys.exit(rc)


if __name__ == "__main__":
    main()
