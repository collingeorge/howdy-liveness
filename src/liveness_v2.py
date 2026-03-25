"""Howdy liveness v2 — face-bounded IR liveness detection.

Changes from v1:
  - Face-bounded ROI via OpenCV Haar cascade on IR-on frames
  - IR-on bounding box applied to paired IR-off frame (same spatial region)
  - Fallback to central 50% ROI when no face detected in IR-on frame
  - MIN_FACE_FRAMES checked across ALL frames (not per parity)
  - Phase detection uses face ROI, not background-contaminated center crop
  - Normalized variance compensates for ambient IR across lighting conditions
  - V4L2 backend, stderr cleanup, fail-secure
"""

import cv2, numpy as np, syslog, time, os, sys, warnings

# ── Suppress all noise ──────────────────────────────────────────────
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
warnings.filterwarnings("ignore")

try:
    _devnull = os.open(os.devnull, os.O_WRONLY)
    _stderr_backup = os.dup(2)
except OSError:
    _devnull = _stderr_backup = None

def _suppress_stderr():
    if _devnull is not None:
        os.dup2(_devnull, 2)

def _restore_stderr():
    if _stderr_backup is not None:
        os.dup2(_stderr_backup, 2)

def _cleanup_fds():
    try:
        if _devnull is not None:
            os.close(_devnull)
    except OSError:
        pass
    try:
        if _stderr_backup is not None:
            os.close(_stderr_backup)
    except OSError:
        pass

# ── Thresholds ───────────────────────────────────────────────────────
NORM_VARIANCE_MAX = 55.0     # Above this = screen spoof
PHASE_FRAMES = 20            # Frames for IR emitter phase detection
WARMUP_FRAMES = 30           # Extended warmup for AGC stabilization
SAMPLE_FRAMES = 60           # Measurement frame PAIRS
LIVENESS_TIMEOUT = 25.0      # Total timeout in seconds
MIN_FACE_FRAMES = 10         # Minimum face detections across ALL frames (total, not per parity)

# ── Haar cascade ─────────────────────────────────────────────────────
_cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
_face_cascade = cv2.CascadeClassifier(_cascade_path)
if _face_cascade.empty():
    raise RuntimeError(f"Failed to load Haar cascade: {_cascade_path}")


def _detect_face_bbox(gray_frame):
    """Detect largest face; return (x, y, w, h) or None."""
    faces = _face_cascade.detectMultiScale(
        gray_frame, scaleFactor=1.3, minNeighbors=3, minSize=(60, 60),
        flags=cv2.CASCADE_SCALE_IMAGE)
    if len(faces) == 0:
        return None
    best = max(faces, key=lambda f: f[2] * f[3])
    return tuple(best)


def _extract_roi(gray_frame, bbox):
    """Extract ROI from bounding box. Fallback to center 50% if bbox is None."""
    if bbox is not None:
        x, y, w, h = bbox
        return gray_frame[y:y+h, x:x+w]
    fh, fw = gray_frame.shape
    return gray_frame[fh//4:3*fh//4, fw//4:3*fw//4]


def check_liveness(device_path=None, cap=None):
    syslog.openlog("[HOWDY-LIVENESS]", 0, syslog.LOG_AUTH)
    owns_cap = False
    start_time = time.monotonic()

    try:
        if cap is None:
            if device_path is None:
                device_path = "/dev/video2"
            _suppress_stderr()
            cap = cv2.VideoCapture(device_path, cv2.CAP_V4L2)
            _restore_stderr()
            if not cap.isOpened():
                syslog.syslog(syslog.LOG_ERR,
                    "Liveness FAILED: could not open camera")
                return False
            owns_cap = True

        # ── Phase detection ─────────────────────────────────────
        odd_vals, even_vals = [], []
        phase_total_reads = 0
        captured_idx = 0
        while len(odd_vals) < PHASE_FRAMES // 2 or len(even_vals) < PHASE_FRAMES // 2:
            if time.monotonic() - start_time > 5.0:
                syslog.syslog(syslog.LOG_WARNING,
                    "Liveness FAILED: phase detection timeout")
                return False
            _suppress_stderr()
            ret, frame = cap.read()
            _restore_stderr()
            if not ret:
                phase_total_reads += 1
                if phase_total_reads > PHASE_FRAMES * 4:
                    syslog.syslog(syslog.LOG_ERR,
                        "Liveness FAILED: camera not returning frames during phase detection")
                    return False
                continue

            phase_total_reads += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape
            face = gray[h//4:3*h//4, w//4:3*w//4]
            mean_val = float(np.mean(face))
            if captured_idx % 2 == 0:
                even_vals.append(mean_val)
            else:
                odd_vals.append(mean_val)
            captured_idx += 1

        odd_mean = np.mean(odd_vals)
        even_mean = np.mean(even_vals)
        ir_on_parity = 1 if odd_mean > even_mean else 0

        syslog.syslog(syslog.LOG_INFO,
            f"Phase: odd_mean={odd_mean:.2f} even_mean={even_mean:.2f} "
            f"ir_on_parity={ir_on_parity}")

        # ── AGC warmup ──────────────────────────────────────────
        warmup_count = 0
        while warmup_count < WARMUP_FRAMES:
            if time.monotonic() - start_time > LIVENESS_TIMEOUT:
                syslog.syslog(syslog.LOG_WARNING,
                    "Liveness FAILED: warmup timeout")
                return False
            _suppress_stderr()
            ret, frame = cap.read()
            _restore_stderr()
            if ret:
                warmup_count += 1

        # ── Sample collection in PAIRS ────────────────────────
        # Read two consecutive frames per iteration.
        # Detect face in the IR-on frame, apply same bbox to IR-off frame.
        on_frames, off_frames = [], []
        total_face_frames = 0
        pair_count = 0
        total_reads = 0
        max_reads = SAMPLE_FRAMES * 6

        while pair_count < SAMPLE_FRAMES and total_reads < max_reads:
            if time.monotonic() - start_time > LIVENESS_TIMEOUT:
                syslog.syslog(syslog.LOG_WARNING,
                    f"Liveness FAILED: sample timeout (pairs={pair_count} "
                    f"face_det={total_face_frames})")
                return False

            # Read frame A
            _suppress_stderr()
            ret_a, frame_a = cap.read()
            _restore_stderr()
            if not ret_a:
                total_reads += 1
                continue
            total_reads += 1

            # Read frame B
            _suppress_stderr()
            ret_b, frame_b = cap.read()
            _restore_stderr()
            if not ret_b:
                total_reads += 1
                continue
            total_reads += 1

            gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
            gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)

            # Determine which frame in the pair is IR-on vs IR-off.
            # pair_count tracks how many pairs we've consumed.
            # Frame A's global index = PHASE_FRAMES + WARMUP_FRAMES + pair_count*2
            # Frame B's global index = that + 1
            # We use pair_count*2 parity to assign:
            frame_a_global_idx = pair_count * 2
            if frame_a_global_idx % 2 == ir_on_parity:
                on_gray, off_gray = gray_a, gray_b
            else:
                on_gray, off_gray = gray_b, gray_a

            # Detect face in IR-on frame (bright — Haar works here)
            bbox = _detect_face_bbox(on_gray)
            if bbox is not None:
                total_face_frames += 1

            # Apply SAME bounding box to both frames
            on_roi = _extract_roi(on_gray, bbox)
            off_roi = _extract_roi(off_gray, bbox)

            on_frames.append(on_roi.astype(np.float64))
            off_frames.append(off_roi.astype(np.float64))
            pair_count += 1

        syslog.syslog(syslog.LOG_INFO,
            f"Capture: pairs={pair_count} face_det={total_face_frames} "
            f"total_reads={total_reads}")

        # ── Fail-secure: minimum face detections (total, not per parity) ──
        if total_face_frames < MIN_FACE_FRAMES:
            syslog.syslog(syslog.LOG_ERR,
                f"Liveness FAILED: only {total_face_frames} face detections "
                f"(need {MIN_FACE_FRAMES})")
            return False

        if len(on_frames) < 10 or len(off_frames) < 10:
            syslog.syslog(syslog.LOG_ERR,
                f"Liveness FAILED: insufficient frame pairs "
                f"(on={len(on_frames)} off={len(off_frames)})")
            return False

        # ── Resize ROIs to common dimensions for stacking ─────
        heights = [f.shape[0] for f in on_frames + off_frames]
        widths = [f.shape[1] for f in on_frames + off_frames]
        th, tw = int(np.median(heights)), int(np.median(widths))

        def resize_stack(frames):
            resized = []
            for f in frames:
                if f.shape[0] != th or f.shape[1] != tw:
                    resized.append(cv2.resize(f, (tw, th),
                        interpolation=cv2.INTER_LINEAR))
                else:
                    resized.append(f)
            return np.array(resized)

        on_arr = resize_stack(on_frames)
        off_arr = resize_stack(off_frames)

        delta_map = np.mean(on_arr, axis=0) - np.mean(off_arr, axis=0)
        delta_mean = float(np.mean(delta_map))
        spatial_variance = float(np.var(delta_map))
        mean_intensity = (float(np.mean(on_arr)) + float(np.mean(off_arr))) / 2.0
        normalized_variance = spatial_variance / mean_intensity if mean_intensity > 0 else 9999.0

        syslog.syslog(syslog.LOG_INFO,
            f"Liveness: delta_mean={delta_mean:.2f} spatial_var={spatial_variance:.2f} "
            f"mean_ir={mean_intensity:.2f} norm_var={normalized_variance:.4f}")

        # ── Discriminator 1: sign ───────────────────────────────
        if delta_mean <= 0:
            syslog.syslog(syslog.LOG_WARNING,
                f"Liveness FAILED: delta_mean={delta_mean:.2f} <= 0 "
                f"(negative sign indicates spoof)")
            return False

        # ── Discriminator 2: normalized variance ────────────────
        if normalized_variance > NORM_VARIANCE_MAX:
            syslog.syslog(syslog.LOG_WARNING,
                f"Liveness FAILED: norm_var={normalized_variance:.4f} > {NORM_VARIANCE_MAX} "
                f"(high variance indicates screen spoof)")
            return False

        # ── PASSED ──────────────────────────────────────────────
        syslog.syslog(syslog.LOG_INFO,
            f"Liveness PASSED: delta_mean={delta_mean:.2f} "
            f"norm_var={normalized_variance:.4f}")
        return True

    except Exception as e:
        syslog.syslog(syslog.LOG_ERR,
            f"Liveness FAILED: exception: {e}")
        return False
    finally:
        if owns_cap and cap is not None:
            try:
                cap.release()
            except Exception:
                pass
        try:
            _restore_stderr()
        finally:
            _cleanup_fds()
        syslog.closelog()


if __name__ == "__main__":
    print("=" * 60)
    print("Howdy Liveness v2 — standalone test")
    print("=" * 60)

    _orig_syslog = syslog.syslog
    def _verbose_syslog(priority, msg):
        labels = {
            syslog.LOG_INFO: "INFO",
            syslog.LOG_WARNING: "WARN",
            syslog.LOG_ERR: "ERR ",
        }
        label = labels.get(priority, "????")
        print(f"  [{label}] {msg}")
        _orig_syslog(priority, msg)
    syslog.syslog = _verbose_syslog

    result = check_liveness()
    print("=" * 60)
    print(f"Result: {'LIVE' if result else 'SPOOF DETECTED'}")
    print("=" * 60)
    sys.exit(0 if result else 1)
