"""Generate a printable checkerboard pattern for stereo calibration.

Usage:
    python -m osc_tracking.tools.generate_checkerboard

Outputs: checkerboard_9x6_25mm.png (A4 size, 300dpi)
"""

import cv2
import numpy as np


def main():
    cols, rows = 9, 6
    square_mm = 25
    dpi = 300
    margin_mm = 15

    px_per_mm = dpi / 25.4
    square_px = int(square_mm * px_per_mm)
    margin_px = int(margin_mm * px_per_mm)

    board_w = (cols + 1) * square_px
    board_h = (rows + 1) * square_px
    img_w = board_w + 2 * margin_px
    img_h = board_h + 2 * margin_px

    img = np.ones((img_h, img_w), dtype=np.uint8) * 255

    for r in range(rows + 1):
        for c in range(cols + 1):
            if (r + c) % 2 == 0:
                x = margin_px + c * square_px
                y = margin_px + r * square_px
                img[y:y + square_px, x:x + square_px] = 0

    # Add label
    label = f"Checkerboard {cols}x{rows} internal corners, {square_mm}mm squares"
    font_scale = square_px / 80
    cv2.putText(img, label, (margin_px, img_h - margin_px // 2),
                cv2.FONT_HERSHEY_SIMPLEX, font_scale, 0, 2)

    filename = f"checkerboard_{cols}x{rows}_{square_mm}mm.png"
    cv2.imwrite(filename, img)
    print(f"Saved: {filename} ({img_w}x{img_h}px, {dpi}dpi)")
    print("Print at 100% scale on A4 paper.")


if __name__ == "__main__":
    main()
