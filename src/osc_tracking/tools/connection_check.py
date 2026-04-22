"""Connection check tool  - verify SlimeVR Server OSC output.

Listens for OSC messages and reports what's coming in.
Use this before running the full tracker to confirm SlimeVR Server
(and SlimeTora for HaritoraX2) are sending data correctly.

Usage:
    python -m osc_tracking.tools.connection_check
    python -m osc_tracking.tools.connection_check --port 6969 --duration 30
"""

import argparse
import sys
import time
from collections import defaultdict

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

# ANSI colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OSC Connection Check  - verify SlimeVR Server output"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Listen host")
    parser.add_argument("--port", type=int, default=6969, help="Listen port")
    parser.add_argument("--duration", type=int, default=30, help="Listen duration (seconds)")
    args = parser.parse_args()

    print(f"{CYAN}{'=' * 55}")
    print("  OSC Connection Check")
    print(f"  Listening on {args.host}:{args.port} for {args.duration}s")
    print(f"{'=' * 55}{RESET}")
    print()
    print("  Waiting for OSC messages from SlimeVR Server...")
    print("  Make sure SlimeVR Server is running (HaritoraX2 also needs SlimeTora).")
    print()

    # Track received data
    stats: dict[str, list[float]] = defaultdict(list)
    message_count = 0
    first_message_time = 0.0

    def handle_message(address: str, *args_osc: float) -> None:
        nonlocal message_count, first_message_time
        now = time.monotonic()
        if message_count == 0:
            first_message_time = now
            print(f"  {GREEN}First message received!{RESET}")
        message_count += 1
        stats[address].append(now)

        # Print first few messages verbosely
        if message_count <= 16:
            values = ", ".join(f"{v:.4f}" for v in args_osc[:4])
            print(f"  {address}: [{values}]")

    dispatcher = Dispatcher()
    dispatcher.set_default_handler(handle_message)

    try:
        server = BlockingOSCUDPServer((args.host, args.port), dispatcher)
    except OSError as e:
        print(f"  {RED}ERROR: Cannot bind to port {args.port}: {e}{RESET}")
        print("  Is another instance already running?")
        sys.exit(1)

    import threading
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    # Wait for duration
    start = time.monotonic()
    try:
        while time.monotonic() - start < args.duration:
            elapsed = time.monotonic() - start
            remaining = args.duration - elapsed
            if message_count > 0 and int(elapsed) % 5 == 0 and int(elapsed) > 0:
                fps = message_count / (time.monotonic() - first_message_time) if first_message_time > 0 else 0
                print(f"  ... {message_count} messages, {fps:.0f} msg/s, {remaining:.0f}s remaining")
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass

    server.shutdown()

    # Summary
    print()
    print(f"{CYAN}{'=' * 55}")
    print("  Connection Check Summary")
    print(f"{'=' * 55}{RESET}")
    print()

    if message_count == 0:
        print(f"  {RED}NO MESSAGES RECEIVED{RESET}")
        print()
        print("  Troubleshooting:")
        print("  1. (HaritoraX2) Is SlimeTora running and connected to your trackers?")
        print("  2. Is SlimeVR Server running and recognizing your trackers?")
        print("  3. Is SlimeVR Server configured to output OSC on port", args.port, "?")
        print("  4. Is another program using port", args.port, "?")
        sys.exit(1)

    duration = time.monotonic() - first_message_time
    overall_fps = message_count / max(duration, 0.001)

    print(f"  {GREEN}Messages received: {message_count}{RESET}")
    print(f"  Duration: {duration:.1f}s")
    print(f"  Average rate: {overall_fps:.1f} msg/s")
    print()

    # Per-address breakdown
    print(f"  {'Address':<45} {'Count':>6} {'Rate':>8}")
    print(f"  {'-' * 60}")
    for address, times in sorted(stats.items()):
        count = len(times)
        if len(times) > 1:
            addr_duration = times[-1] - times[0]
            rate = count / max(addr_duration, 0.001)
        else:
            rate = 0
        print(f"  {address:<45} {count:>6} {rate:>7.1f}/s")

    print()

    # Health assessment
    unique_addresses = len(stats)
    rotation_addresses = [a for a in stats if "rotation" in a]

    if len(rotation_addresses) >= 6:
        print(f"  {GREEN}HEALTH: GOOD  - {len(rotation_addresses)} rotation trackers detected{RESET}")
    elif len(rotation_addresses) >= 1:
        print(f"  {YELLOW}HEALTH: PARTIAL  - only {len(rotation_addresses)} rotation trackers{RESET}")
        print("  Expected 6-8 trackers (e.g. HaritoraX2 is 8)")
    else:
        print(f"  {RED}HEALTH: NO ROTATION DATA  - check SlimeVR Server OSC config{RESET}")

    print()
    print(f"  Total unique addresses: {unique_addresses}")
    print(f"  Rotation addresses: {len(rotation_addresses)}")
    print()

    if len(rotation_addresses) >= 6 and overall_fps > 10:
        print(f"  {GREEN}Ready for tracking! Run: python -m osc_tracking.main{RESET}")
    else:
        print(f"  {YELLOW}Fix issues above before running the tracker.{RESET}")


if __name__ == "__main__":
    main()
