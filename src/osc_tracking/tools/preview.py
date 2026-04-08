"""Camera preview with MediaPipe landmark overlay.

Usage:
    python -m osc_tracking.tools.preview --cam1 0 --cam2 1

Shows both camera feeds side-by-side with MediaPipe pose landmarks
drawn on top. Useful for verifying camera setup before running
the full tracking pipeline.
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(description="Camera preview with landmarks")
    parser.add_argument("--cam1", type=int, default=0)
    parser.add_argument("--cam2", type=int, default=1)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument(
        "--model", type=str, default="models/pose_landmarker_heavy.task",
        help="Path to MediaPipe Pose Landmarker model",
    )
    args = parser.parse_args()

    cap1 = cv2.VideoCapture(args.cam1)
    cap2 = cv2.VideoCapture(args.cam2)
    for cap in (cap1, cap2):
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    if not cap1.isOpened():
        print(f"ERROR: Camera {args.cam1} not found")
        sys.exit(1)
    if not cap2.isOpened():
        print(f"ERROR: Camera {args.cam2} not found")
        sys.exit(1)

    # Try to load MediaPipe
    pose1, pose2 = None, None
    try:
        import mediapipe as mp_lib
        from mediapipe.tasks.python import BaseOptions, vision

        if Path(args.model).exists():
            options = vision.PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=args.model),
                running_mode=vision.RunningMode.VIDEO,
                num_poses=1,
            )
            pose1 = vision.PoseLandmarker.create_from_options(options)
            pose2 = vision.PoseLandmarker.create_from_options(options)
            print(f"MediaPipe loaded: {args.model}")
        else:
            print(f"Model not found at {args.model} — showing cameras only")
    except Exception as e:
        print(f"MediaPipe not available: {e}")

    print("\nCamera Preview")
    print("  q = quit")
    print()

    # Landmark connections for drawing skeleton
    POSE_CONNECTIONS = [
        (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),  # arms
        (11, 23), (12, 24), (23, 24),  # torso
        (23, 25), (25, 27), (24, 26), (26, 28),  # legs
        (0, 11), (0, 12),  # head to shoulders
    ]

    frame_ts_ms = 0

    while True:
        ret1, frame1 = cap1.read()
        ret2, frame2 = cap2.read()
        if not ret1 or not ret2:
            continue

        frame_ts_ms += 33  # ~30fps

        display1 = frame1.copy()
        display2 = frame2.copy()

        if pose1 is not None and pose2 is not None:
            try:
                import mediapipe as mp_lib

                rgb1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2RGB)
                rgb2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2RGB)

                mp_img1 = mp_lib.Image(image_format=mp_lib.ImageFormat.SRGB, data=rgb1)
                mp_img2 = mp_lib.Image(image_format=mp_lib.ImageFormat.SRGB, data=rgb2)

                r1 = pose1.detect_for_video(mp_img1, frame_ts_ms)
                r2 = pose2.detect_for_video(mp_img2, frame_ts_ms)

                if r1.pose_landmarks:
                    _draw_landmarks(display1, r1.pose_landmarks[0], POSE_CONNECTIONS, args.width, args.height)
                if r2.pose_landmarks:
                    _draw_landmarks(display2, r2.pose_landmarks[0], POSE_CONNECTIONS, args.width, args.height)

                # Show confidence
                if r1.pose_landmarks:
                    avg_vis = np.mean([lm.visibility for lm in r1.pose_landmarks[0] if hasattr(lm, 'visibility')])
                    _draw_confidence_bar(display1, avg_vis)
                if r2.pose_landmarks:
                    avg_vis = np.mean([lm.visibility for lm in r2.pose_landmarks[0] if hasattr(lm, 'visibility')])
                    _draw_confidence_bar(display2, avg_vis)

            except Exception as e:
                cv2.putText(display1, f"Error: {e}", (10, 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        cv2.putText(display1, "Camera 1", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(display2, "Camera 2", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        combined = np.hstack([display1, display2])
        cv2.imshow("Camera Preview - Press Q to quit", combined)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap1.release()
    cap2.release()
    if pose1:
        pose1.close()
    if pose2:
        pose2.close()
    cv2.destroyAllWindows()


def _draw_landmarks(frame, landmarks, connections, w, h):
    """Draw pose landmarks and skeleton on frame."""
    points = {}
    for i, lm in enumerate(landmarks):
        px = int(lm.x * w)
        py = int(lm.y * h)
        points[i] = (px, py)

        vis = lm.visibility if hasattr(lm, 'visibility') else 0.5
        if vis > 0.5:
            color = (0, 255, 0)
        elif vis > 0.3:
            color = (0, 165, 255)
        else:
            color = (0, 0, 255)

        cv2.circle(frame, (px, py), 4, color, -1)

    for a, b in connections:
        if a in points and b in points:
            cv2.line(frame, points[a], points[b], (255, 255, 255), 2)


def _draw_confidence_bar(frame, confidence):
    """Draw a confidence bar at the bottom of the frame."""
    h, w = frame.shape[:2]
    bar_h = 20
    bar_w = int(w * 0.8)
    x_start = int(w * 0.1)
    y = h - 30

    # Background
    cv2.rectangle(frame, (x_start, y), (x_start + bar_w, y + bar_h), (50, 50, 50), -1)

    # Fill
    fill_w = int(bar_w * confidence)
    if confidence > 0.7:
        color = (0, 200, 0)
    elif confidence > 0.3:
        color = (0, 165, 255)
    else:
        color = (0, 0, 200)
    cv2.rectangle(frame, (x_start, y), (x_start + fill_w, y + bar_h), color, -1)

    # Text
    cv2.putText(frame, f"Conf: {confidence:.1%}", (x_start + 5, y + 15),
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)


if __name__ == "__main__":
    main()
