# Howdy Liveness Detection

Passive IR Reflectance Analysis for Anti-Spoofing in Linux PAM Facial Authentication

![Status](https://img.shields.io/badge/Status-Active%20Research-green)
![Project Type](https://img.shields.io/badge/Project-Security%20Research-blue)
![Version](https://img.shields.io/badge/Version-1.4-green)
![Last Updated](https://img.shields.io/badge/Updated-March%202026-lightgrey)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC_BY_4.0-blue.svg)](https://creativecommons.org/licenses/by/4.0/)

---

## Overview

This repository presents a passive infrared (IR) reflectance analysis method for anti-spoofing liveness detection in [Howdy](https://github.com/boltgolt/howdy) — the primary open-source implementation of Windows Hello-style facial authentication for Linux.

Howdy provides PAM-integrated biometric login but has no liveness detection. A photograph or screen displaying an enrolled user's face will authenticate successfully. This implementation addresses that vulnerability using only the hardware already present in IR-equipped laptops — no additional sensors required.

Developed, implemented, and validated on Ubuntu 24.04 LTS with a Microsoft Surface Pro IR camera across 84 total measurement sessions plus 10 PAM-context calibration sessions. The companion research paper is included in `docs/`.

---

## Repository Contents

| File | Description |
|------|-------------|
| [src/liveness.py](src/liveness.py) | **Core liveness detection module** — passive IR reflectance analysis with sign and spatial variance discrimination |
| [src/compare_patched.py](src/compare_patched.py) | Patched Howdy `compare.py` with liveness integration and security fixes |
| [src/pam_patched.py](src/pam_patched.py) | Patched Howdy `pam.py` with exit code 14 handler and subprocess timeout |
| [src/add_patched.py](src/add_patched.py) | Patched Howdy `add.py` with multi-frame enrollment |
| [data/ir_measurements.json](data/ir_measurements.json) | Raw empirical IR measurements (n=8 live, n=34 screen, n=38 photo) |
| [data/outlier_sessions.json](data/outlier_sessions.json) | Full disclosure of 4 excluded sessions with exclusion rationale |
| [data/threshold_calibration.json](data/threshold_calibration.json) | PAM-context threshold calibration history (400 → 700 → 800) |
| [docs/George-SEC-LIV-01-v1.4.pdf](docs/George-SEC-LIV-01-v1.4.pdf) | **Full research paper (PDF)** — SEC-LIV-01 v1.4, arXiv submission version |
| [docs/George-SEC-LIV-01-v1.4.docx](docs/George-SEC-LIV-01-v1.4.docx) | Full research paper (Word) |
| [CITATION.cff](CITATION.cff) | Formal citation metadata |
| [LICENSE](LICENSE) | CC BY 4.0 |

---

## The Problem

Howdy authenticates using facial recognition but has no liveness detection. Any photograph or screen displaying the enrolled user's face will authenticate successfully. This is a known limitation affecting all Howdy installations on Linux.

Windows Hello addresses this using depth sensing and IR liveness analysis at the firmware level. No equivalent implementation exists for Linux.

---

## Approach

Consumer IR cameras emit infrared light in an alternating on/off flash cycle at approximately 60fps. Two complementary discriminators emerge from multi-session empirical measurement:

**Discriminator 1 — Delta Sign (zero-parameter):** Live facial tissue produces consistently positive IR delta values. Both spoofing materials produce negative delta values. Correct across all 80 valid sessions.

**Discriminator 2 — Spatial Variance (threshold):** The spatial variance of the per-pixel IR delta map discriminates live tissue from spoofing materials.

| Material | Delta Sign | Spatial Variance (standalone) | Sessions |
|----------|-----------|-------------------------------|---------|
| Live face | Positive (8/8) | 232.74 ± 5.51 (max: 241.65) | 8 |
| Printed photo | Negative (38/38) | 2,793.5 ± 385.2 (min: 1,817.3) | 38 |
| Phone screen | Negative (34/34) | 2,897.5 ± 415.3 (min: 2,246.4) | 34 |

**Important:** Threshold calibration must be performed in PAM authentication context, not standalone. The camera produces higher spatial variance in PAM context (live max: 590.57) than standalone (live max: 241.65) due to camera state differences when sharing an already-initialized VideoCapture object. The threshold is calibrated to 800 based on 10 consecutive PAM-context sessions.

---

## Hardware

Tested on:
- Microsoft Surface Pro (2019), Surface Camera Front (045e:0990)
- Ubuntu 24.04 LTS
- Howdy 2.6.1
- Python 3.12, OpenCV 4.13, dlib 20.0

Compatible with any IR camera that uses alternating IR emitter flash cycling. **Recalibrate the spatial variance threshold in PAM context for your hardware.**

---

## Installation

### Prerequisites

```bash
sudo apt install howdy
sudo pip install opencv-python dlib face_recognition --break-system-packages
```

### Install Liveness Module

```bash
sudo cp src/liveness.py /lib/security/howdy/liveness.py
```

### Patch compare.py

Add after `from recorders.video_capture import VideoCapture`:

```python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from liveness import check_liveness
```

Add after `video_capture = VideoCapture(config)`:

```python
if not check_liveness(cap=video_capture.internal):
    sys.exit(14)
```

### Patch pam.py

Add exit code 14 handler after the status 13 block:

```python
elif status == 14:
    syslog.syslog(syslog.LOG_WARNING, "Failure, liveness check failed - spoof attempt detected")
    syslog.closelog()
    pamh.conversation(pamh.Message(pamh.PAM_ERROR_MSG, "Liveness check failed"))
    return pamh.PAM_AUTH_ERR
```

---

## Configuration

Thresholds in `liveness.py`:

```python
DELTA_MEAN_THRESHOLD = 0      # Live tissue: positive. Both spoofs: negative (zero-parameter)
SPATIAL_VARIANCE_MAX = 800.0  # PAM-context calibrated. Live PAM-context max: 590.57.
                               # Nearest spoof min: 1,817.3 (2.27× safety margin)
WARMUP_FRAMES = 10            # Required — insufficient warmup elevates live SV above threshold
SAMPLE_FRAMES = 60
LIVENESS_TIMEOUT = 15.0       # Prevents indefinite PAM hang on camera stall
```

**Calibration note:** If you experience frequent false rejections, monitor syslog during authentication (`sudo journalctl -f | grep HOWDY-LIVENESS`) and raise `SPATIAL_VARIANCE_MAX` until you achieve consistent passes. Always calibrate in PAM context, not standalone.

---

## Multi-Factor Authentication Stack

The liveness module was deployed as part of a three-factor authentication stack requiring no proprietary software or custom hardware beyond what is already present on the device:

| Factor | Implementation | Defeats |
|--------|---------------|---------|
| Possession | YubiKey 5Ci FIPS (FIDO2 via pam_u2f) | Remote credential theft, password replay |
| Presence | IR liveness detection (this module) | Photograph and screen spoofing |
| Identity | Howdy face recognition | Identity verification |

### PAM Configuration

**`/etc/pam.d/sudo`** — YubiKey required first, then Howdy:
```
auth required pam_u2f.so cue
@include common-auth
```

**`/etc/pam.d/common-auth`** — Howdy with liveness:
```
auth [success=2 default=ignore] pam_python.so /lib/security/howdy/pam.py
```

**`/etc/pam.d/gdm-password`** — same pattern for screen unlock:
```
auth required pam_u2f.so
@include common-auth
```

An adversary who defeats liveness detection still cannot authenticate without the physical YubiKey. An adversary with the YubiKey but without the enrolled face is rejected by face recognition and liveness. 3D mask attacks are not addressed — blink detection is the identified mitigation path.



```bash
# Monitor live authentication values
sudo journalctl -f | grep HOWDY-LIVENESS

# Standalone test (note: spatial variance will be lower than PAM context)
sudo python3 /lib/security/howdy/liveness.py
```

---

## Empirical Data

Raw measurements in `data/ir_measurements.json`. Four outlier sessions disclosed in `data/outlier_sessions.json`. Threshold calibration history in `data/threshold_calibration.json`.

---

## Limitations

- Single-subject evaluation — recalibrate for other subjects and hardware
- Sign discriminator for printed-photo attacks depends on camera AGC behavior
- 3D mask attacks not tested — blink detection is the identified mitigation path
- Variable/high-ambient-IR lighting not characterized — primary false-positive risk
- Spatial variance threshold must be calibrated in PAM context, not standalone

---

## Security Fixes Applied

The patched source files include the following security improvements over stock Howdy:

- Path traversal prevention via username validation regex
- Subprocess timeout in pam.py (prevents indefinite PAM hang)
- Frame capture timeout in liveness.py (prevents indefinite auth hang)
- File handle leak fixes (syslog, open())
- Division by zero guard on empty histogram
- Python 3.12 compatibility (datetime.timezone.utc)
- Removal of stale Python 2 comments

---

## Future Work

- Blink detection challenge-response (highest priority)
- Multi-subject PAM-context calibration
- Variable lighting characterization
- AGC-independent sign discriminator validation
- Cross-hardware threshold characterization

---

## Citation

**Vancouver**

George CB. Passive IR reflectance analysis for anti-spoofing liveness detection in Linux PAM-integrated facial authentication [Internet]. 2026. Available from: https://github.com/collingeorge/howdy-liveness

**APA**

George, C. B. (2026). *Passive IR reflectance analysis for anti-spoofing liveness detection in Linux PAM-integrated facial authentication*. GitHub. https://github.com/collingeorge/howdy-liveness

---

## Author

**Collin B. George, BS**
ORCID: 0009-0007-8162-6839
GitHub: [github.com/collingeorge](https://github.com/collingeorge)
Affiliation: Center for Competitive Statecraft and Strategic Policy

This is an independent research contribution. It is not affiliated with, endorsed by, or issued on behalf of any institution. All interpretations, conclusions, and any errors are solely the responsibility of the author.

---

## License

Licensed under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).

© 2026 Collin B. George — https://github.com/collingeorge/howdy-liveness
