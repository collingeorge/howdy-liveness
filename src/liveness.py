import cv2, numpy as np, syslog, time, os, warnings
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
warnings.filterwarnings("ignore")

# Thresholds calibrated from empirical measurements:
# Live face:     delta_mean 49-55,  normalized_variance 12-48
# Printed photo: delta_mean 67-82,  normalized_variance 31-51
# Phone screen:  delta_mean 30-55,  normalized_variance 65-123
#
# Discriminators:
#   1. delta_mean <= 0    → FAIL (sign: live tissue always positive)
#   2. delta_mean > 63    → FAIL (catches printed photo; live max observed 55)
#   3. normalized_var > 55 → FAIL (catches phone screen; live max observed 48)
#
# Phase detection: IR emitter parity detected empirically each run
# rather than assuming odd=IR-on. Eliminates ambient IR sensitivity.

DELTA_MEAN_CEIL = 63.0       # Above this = printed photo spoof
NORM_VARIANCE_MAX = 55.0     # Above this = screen spoof
PHASE_FRAMES = 20            # Frames for IR emitter phase detection
WARMUP_FRAMES = 30           # Extended warmup for AGC stabilization
SAMPLE_FRAMES = 60           # Measurement frames
LIVENESS_TIMEOUT = 20.0      # Total timeout in seconds


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

    start_time = time.monotonic()

    # Phase detection — detect actual IR emitter on/off parity
    odd_sum, even_sum, phase_count = 0.0, 0.0, 0
    while phase_count < PHASE_FRAMES:
        if time.monotonic() - start_time > 5.0:
            syslog.syslog(syslog.LOG_WARNING, "Liveness FAILED: phase detection timeout")
            syslog.closelog()
            if owns_cap: cap.release()
            return False
        ret, frame = cap.read()
        if not ret:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        face = gray[h//4:3*h//4, w//4:3*w//4]
        if phase_count % 2 == 1:
            odd_sum += float(np.mean(face))
        else:
            even_sum += float(np.mean(face))
        phase_count += 1

    # IR-on frames have higher mean intensity
    ir_on_parity = 1 if odd_sum > even_sum else 0
    syslog.syslog(syslog.LOG_INFO,
        f"Phase: odd_mean={odd_sum/10:.2f} even_mean={even_sum/10:.2f} ir_on_parity={ir_on_parity}")

    # Extended warmup for AGC stabilization
    warmup_count = 0
    while warmup_count < WARMUP_FRAMES:
        if time.monotonic() - start_time > LIVENESS_TIMEOUT:
            syslog.syslog(syslog.LOG_WARNING, "Liveness FAILED: warmup timeout")
            syslog.closelog()
            if owns_cap: cap.release()
            return False
        ret, frame = cap.read()
        if ret:
            warmup_count += 1

    # Collect sample frames
    on_frames, off_frames, frame_count = [], [], 0
    while frame_count < SAMPLE_FRAMES * 2:
        if time.monotonic() - start_time > LIVENESS_TIMEOUT:
            syslog.syslog(syslog.LOG_WARNING, "Liveness FAILED: sample timeout")
            syslog.closelog()
            if owns_cap: cap.release()
            return False
        ret, frame = cap.read()
        if not ret:
            frame_count += 1
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        face = gray[h//4:3*h//4, w//4:3*w//4]
        if frame_count % 2 == ir_on_parity:
            on_frames.append(face.astype(float))
        else:
            off_frames.append(face.astype(float))
        frame_count += 1

    if owns_cap:
        cap.release()

    if len(on_frames) < 10 or len(off_frames) < 10:
        syslog.syslog(syslog.LOG_ERR, "Liveness FAILED: insufficient frames")
        syslog.closelog()
        return False

    on_arr = np.array(on_frames)
    off_arr = np.array(off_frames)
    delta_map = np.mean(on_arr, axis=0) - np.mean(off_arr, axis=0)
    delta_mean = float(np.mean(delta_map))
    spatial_variance = float(np.var(delta_map))
    mean_intensity = (float(np.mean(on_arr)) + float(np.mean(off_arr))) / 2.0
    normalized_variance = spatial_variance / mean_intensity if mean_intensity > 0 else 9999.0

    syslog.syslog(syslog.LOG_INFO,
        f"Liveness: delta_mean={delta_mean:.2f} spatial_variance={spatial_variance:.2f} "
        f"mean_intensity={mean_intensity:.2f} normalized_variance={normalized_variance:.4f}")

    # Discriminator 1: sign — live tissue always positive
    if delta_mean <= 0:
        syslog.syslog(syslog.LOG_WARNING,
            f"Liveness FAILED: delta_mean={delta_mean:.2f} <= 0 (negative sign indicates spoof)")
        syslog.closelog()
        return False

    # Discriminator 2: delta_mean ceiling — catches printed photo
    if delta_mean > DELTA_MEAN_CEIL:
        syslog.syslog(syslog.LOG_WARNING,
            f"Liveness FAILED: delta_mean={delta_mean:.2f} > {DELTA_MEAN_CEIL} (high delta indicates print spoof)")
        syslog.closelog()
        return False

    # Discriminator 3: normalized variance — catches screen replay
    if normalized_variance > NORM_VARIANCE_MAX:
        syslog.syslog(syslog.LOG_WARNING,
            f"Liveness FAILED: normalized_variance={normalized_variance:.4f} > {NORM_VARIANCE_MAX}")
        syslog.closelog()
        return False

    syslog.syslog(syslog.LOG_INFO,
        f"Liveness PASSED: delta_mean={delta_mean:.2f} normalized_variance={normalized_variance:.4f}")
    syslog.closelog()
    return True


if __name__ == "__main__":
    result = check_liveness()
    print("LIVE" if result else "SPOOF DETECTED")
