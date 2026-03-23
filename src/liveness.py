# Howdy liveness detection module
# Detects photo and screen spoofing via IR reflectance analysis
# Based on empirical measurements:
#   Live skin:      delta_mean ~14, spatial_variance ~150
#   Printed photo:  delta_mean ~66, spatial_variance ~1111
#   Phone screen:   delta_mean ~33, spatial_variance ~2752

import cv2
import numpy as np
import syslog

# Thresholds with safety margin
DELTA_MEAN_MAX = 40.0
SPATIAL_VARIANCE_MAX = 400.0
WARMUP_FRAMES = 10
SAMPLE_FRAMES = 60

def check_liveness(device_path=None, cap=None):
    """
    Returns True if live face detected, False if spoof detected.
    Accepts either a device path or an existing VideoCapture object.
    """
    syslog.openlog("[HOWDY-LIVENESS]", 0, syslog.LOG_AUTH)

    owns_cap = False
    if cap is None:
        if device_path is None:
            device_path = "/dev/video2"
        cap = cv2.VideoCapture(device_path)
        if not cap.isOpened():
            syslog.syslog(syslog.LOG_ERR, "Could not open camera for liveness check")
            return False
        owns_cap = True

    on_frames = []
    off_frames = []
    frame_count = 0

    while frame_count < WARMUP_FRAMES + SAMPLE_FRAMES * 2:
        ret, frame = cap.read()
        if not ret:
            frame_count += 1
            continue
        if frame_count < WARMUP_FRAMES:
            frame_count += 1
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        face = gray[h//4:3*h//4, w//4:3*w//4]
        if frame_count % 2 == 1:
            on_frames.append(face.astype(float))
        else:
            off_frames.append(face.astype(float))
        frame_count += 1

    if owns_cap:
        cap.release()

    if len(on_frames) < 10 or len(off_frames) < 10:
        syslog.syslog(syslog.LOG_ERR, "Insufficient frames for liveness check")
        return False

    on_arr = np.array(on_frames)
    off_arr = np.array(off_frames)
    delta_map = np.mean(on_arr, axis=0) - np.mean(off_arr, axis=0)

    delta_mean = float(np.mean(delta_map))
    spatial_variance = float(np.var(delta_map))

    syslog.syslog(syslog.LOG_INFO,
        f"Liveness: delta_mean={delta_mean:.2f} spatial_variance={spatial_variance:.2f}")

    if delta_mean > DELTA_MEAN_MAX:
        syslog.syslog(syslog.LOG_WARNING,
            f"Liveness FAILED: delta_mean {delta_mean:.2f} > {DELTA_MEAN_MAX}")
        syslog.closelog()
        return False

    if spatial_variance > SPATIAL_VARIANCE_MAX:
        syslog.syslog(syslog.LOG_WARNING,
            f"Liveness FAILED: spatial_variance {spatial_variance:.2f} > {SPATIAL_VARIANCE_MAX}")
        syslog.closelog()
        return False

    syslog.syslog(syslog.LOG_INFO, "Liveness PASSED")
    syslog.closelog()
    return True

if __name__ == "__main__":
    result = check_liveness()
    print("LIVE" if result else "SPOOF DETECTED")
