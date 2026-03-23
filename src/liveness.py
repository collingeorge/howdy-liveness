import os
import time
import warnings
import cv2
import numpy as np
import syslog

os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
warnings.filterwarnings("ignore")

DELTA_MEAN_MIN = 0.0
SPATIAL_VARIANCE_MAX = 800.0
WARMUP_FRAMES = 10
SAMPLE_FRAMES = 60
LIVENESS_TIMEOUT = 15.0

def check_liveness(device_path=None, cap=None):
    syslog.openlog("[HOWDY-LIVENESS]", 0, syslog.LOG_AUTH)
    owns_cap = False
    if cap is None:
        if device_path is None:
            device_path = "/dev/video2"
        cap = cv2.VideoCapture(device_path)
        if not cap.isOpened():
            syslog.syslog(syslog.LOG_ERR, "Could not open camera for liveness check")
            syslog.closelog()
            return False
        owns_cap = True
    on_frames = []
    off_frames = []
    frame_count = 0
    start_time = time.monotonic()
    while frame_count < WARMUP_FRAMES + SAMPLE_FRAMES * 2:
        if time.monotonic() - start_time > LIVENESS_TIMEOUT:
            syslog.syslog(syslog.LOG_WARNING, "Liveness check timed out")
            syslog.closelog()
            if owns_cap:
                cap.release()
            return False
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
        syslog.closelog()
        return False
    on_arr = np.array(on_frames)
    off_arr = np.array(off_frames)
    delta_map = np.mean(on_arr, axis=0) - np.mean(off_arr, axis=0)
    delta_mean = float(np.mean(delta_map))
    spatial_variance = float(np.var(delta_map))
    syslog.syslog(syslog.LOG_INFO,
        f"Liveness: delta_mean={delta_mean:.2f} spatial_variance={spatial_variance:.2f}")
    if delta_mean <= DELTA_MEAN_MIN:
        syslog.syslog(syslog.LOG_WARNING,
            f"Liveness FAILED: delta_mean={delta_mean:.2f} <= {DELTA_MEAN_MIN} (negative sign indicates spoof)")
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
    devnull = open(os.devnull, 'w')
    old_stderr = os.dup(2)
    os.dup2(devnull.fileno(), 2)
    result = check_liveness()
    os.dup2(old_stderr, 2)
    os.close(old_stderr)
    devnull.close()
    print("LIVE" if result else "SPOOF DETECTED")
