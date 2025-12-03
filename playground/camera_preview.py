#!/usr/bin/env python3
"""
Quick camera preview - captures one frame from each camera and saves as images.
"""

import cv2
from datetime import datetime
from pathlib import Path

# Camera indices (same as record.py)
CAMERAS = {
    "wrist": 2,
    "top": 0,
}

OUTPUT_DIR = Path("camera_previews")
OUTPUT_DIR.mkdir(exist_ok=True)

def capture_preview():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for name, index in CAMERAS.items():
        print(f"Capturing from {name} camera (index {index})...")
        
        cap = cv2.VideoCapture(index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        if not cap.isOpened():
            print(f"  ✗ Failed to open camera {name} (index {index})")
            continue
        
        # Capture a few frames to let camera adjust
        for _ in range(5):
            cap.read()
        
        ret, frame = cap.read()
        cap.release()
        
        if ret:
            filename = OUTPUT_DIR / f"{name}_{timestamp}.jpg"
            cv2.imwrite(str(filename), frame)
            print(f"  ✓ Saved: {filename}")
        else:
            print(f"  ✗ Failed to capture from {name}")
    
    print(f"\nPreviews saved to {OUTPUT_DIR}/")

if __name__ == "__main__":
    capture_preview()
