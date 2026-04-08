"""Stereo camera calibration tool.

Usage:
    python -m osc_tracking.tools.calibrate --cam1 0 --cam2 1

Instructions:
    1. Print a checkerboard pattern (9x6 internal corners, 25mm squares)
    2. Hold the checkerboard so both cameras can see it
    3. Press SPACE to capture a pair (need at least 10 pairs)
    4. Move the board to different angles and distances between captures
    5. Press 'c' to run calibration when done
    6. Press 'q' to quit
"""

import argparse
import sys

import cv2
import numpy as np

from osc_tracking.stereo_calibration import calibrate_stereo, save_calibration


def main():
    parser = argparse.ArgumentParser(description="Stereo camera calibration")
    parser.add_argument("--cam1", type=int, default=0, help="Camera 1 index")
    parser.add_argument("--cam2", type=int, default=1, help="Camera 2 index")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--board-cols", type=int, default=9, help="Checkerboard internal corners (cols)")
    parser.add_argument("--board-rows", type=int, default=6, help="Checkerboard internal corners (rows)")
    parser.add_argument("--square-size", type=float, default=25.0, help="Square size in mm")
    parser.add_argument(
        "--output", type=str, default="calibration_data/stereo_calib.npz",
        help="Output calibration file path",
    )
    args = parser.parse_args()

    board_size = (args.board_cols, args.board_rows)

    print("=== Stereo Camera Calibration ===")
    print(f"Camera 1: index {args.cam1}")
    print(f"Camera 2: index {args.cam2}")
    print(f"Board: {board_size[0]}x{board_size[1]}, square {args.square_size}mm")
    print()
    print("Controls:")
    print("  SPACE  = Capture pair")
    print("  c      = Run calibration")
    print("  q      = Quit")
    print()

    cap1 = cv2.VideoCapture(args.cam1)
    cap2 = cv2.VideoCapture(args.cam2)
    cap1.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap1.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap2.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap2.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    if not cap1.isOpened() or not cap2.isOpened():
        print("ERROR: Could not open one or both cameras.")
        sys.exit(1)

    captured_pairs: list[tuple[np.ndarray, np.ndarray]] = []

    while True:
        ret1, frame1 = cap1.read()
        ret2, frame2 = cap2.read()

        if not ret1 or not ret2:
            print("Camera read failed")
            continue

        # Draw checkerboard detection overlay
        display1 = frame1.copy()
        display2 = frame2.copy()

        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)

        found1, corners1 = cv2.findChessboardCorners(gray1, board_size, None)
        found2, corners2 = cv2.findChessboardCorners(gray2, board_size, None)

        if found1:
            cv2.drawChessboardCorners(display1, board_size, corners1, found1)
        if found2:
            cv2.drawChessboardCorners(display2, board_size, corners2, found2)

        # Status text
        status = f"Pairs: {len(captured_pairs)}/10+"
        if found1 and found2:
            status += " | BOTH DETECTED - Press SPACE"
            color = (0, 255, 0)
        elif found1 or found2:
            status += " | One camera only"
            color = (0, 165, 255)
        else:
            status += " | No board detected"
            color = (0, 0, 255)

        cv2.putText(display1, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.putText(display2, "Camera 2", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        combined = np.hstack([display1, display2])
        cv2.imshow("Stereo Calibration", combined)

        key = cv2.waitKey(1) & 0xFF

        if key == ord(" "):
            if found1 and found2:
                captured_pairs.append((frame1.copy(), frame2.copy()))
                print(f"  Captured pair {len(captured_pairs)}")
            else:
                print("  Board not detected in both cameras!")

        elif key == ord("c"):
            if len(captured_pairs) < 5:
                print(f"  Need at least 5 pairs, have {len(captured_pairs)}")
                continue

            print(f"\nCalibrating with {len(captured_pairs)} pairs...")
            calib = calibrate_stereo(
                captured_pairs,
                board_size=board_size,
                square_size_mm=args.square_size,
            )

            if calib is not None:
                save_calibration(calib, args.output)
                print(f"\nCalibration saved to {args.output}")
                print(f"  RMS reprojection error: {calib.reprojection_error:.4f}")
                print(f"  Baseline: {np.linalg.norm(calib.T):.1f}mm")
                print("\nCalibration complete! You can close the window.")
            else:
                print("\nCalibration FAILED. Try capturing more pairs from different angles.")

        elif key == ord("q"):
            break

    cap1.release()
    cap2.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
