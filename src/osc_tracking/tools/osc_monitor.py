"""OSC monitor — displays all incoming OSC messages for debugging.

Usage:
    python -m osc_tracking.tools.osc_monitor [--port 6969]

Shows all OSC messages received, useful for:
- Verifying SlimeVR Server OSC output (HaritoraX2 via SlimeTora, SlimeVR native, Tundra, etc.)
- Discovering OSC address patterns from any IMU tracker
- Confirming quaternion data format
"""

import argparse
import time
from collections import defaultdict

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer


def main():
    parser = argparse.ArgumentParser(description="OSC message monitor")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6969)
    args = parser.parse_args()

    msg_count = defaultdict(int)
    last_print = time.monotonic()

    def handler(address, *osc_args):
        msg_count[address] += 1
        now = time.monotonic()

        # Print every message for first 5 seconds, then summarize
        nonlocal last_print
        if now - last_print < 5.0 or msg_count[address] <= 3:
            args_str = ", ".join(f"{a:.4f}" if isinstance(a, float) else str(a) for a in osc_args)
            print(f"  {address}  [{args_str}]")

        if now - last_print > 5.0:
            print(f"\n--- Summary ({sum(msg_count.values())} messages) ---")
            for addr, count in sorted(msg_count.items()):
                print(f"  {addr}: {count} msgs")
            print("--- Listening... ---\n")
            last_print = now

    dispatcher = Dispatcher()
    dispatcher.set_default_handler(handler)

    print("=== OSC Monitor ===")
    print(f"Listening on {args.host}:{args.port}")
    print("Press Ctrl+C to stop\n")

    try:
        server = BlockingOSCUDPServer((args.host, args.port), dispatcher)
        server.serve_forever()
    except OSError as e:
        if "Address already in use" in str(e) or e.errno == 10048:
            print(f"ERROR: Port {args.port} is already in use.")
            print(f"Try: python -m osc_tracking.tools.osc_monitor --port {args.port + 1}")
        else:
            raise
    except KeyboardInterrupt:
        print("\n\nFinal summary:")
        for addr, count in sorted(msg_count.items()):
            print(f"  {addr}: {count} messages")


if __name__ == "__main__":
    main()
