# Howdy Liveness Detection

Passive IR Reflectance Analysis for Anti-Spoofing in Linux PAM Facial Authentication

![Status](https://img.shields.io/badge/Status-Active%20Research-green)
![Project Type](https://img.shields.io/badge/Project-Security%20Research-blue)
![Version](https://img.shields.io/badge/Version-1.0-green)
![Last Updated](https://img.shields.io/badge/Updated-March%202026-lightgrey)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC_BY_4.0-blue.svg)](https://creativecommons.org/licenses/by/4.0/)

---

## Overview

This repository presents a passive infrared (IR) reflectance analysis method for anti-spoofing liveness detection in [Howdy](https://github.com/boltgolt/howdy) — the primary open-source implementation of Windows Hello-style facial authentication for Linux.

Howdy provides PAM-integrated biometric login but has no liveness detection. A photograph or screen displaying an enrolled user's face will authenticate successfully. This implementation addresses that vulnerability using only the hardware already present in IR-equipped laptops — no additional sensors required.

Developed, implemented, and validated on Ubuntu 24.04 LTS with a Microsoft Surface Pro IR camera. The companion research paper is included in `docs/`.

---

## Repository Contents

| File | Description |
|------|-------------|
| [src/liveness.py](src/liveness.py) | **Core liveness detection module** — passive IR reflectance analysis with spatial variance discrimination |
| [src/compare_patched.py](src/compare_patched.py) | Patched Howdy `compare.py` with liveness integration |
| [src/pam_patched.py](src/pam_patched.py) | Patched Howdy `pam.py` with exit code 14 (liveness failure) handler |
| [src/add_patched.py](src/add_patched.py) | Patched Howdy `add.py` with multi-frame enrollment |
| [data/ir_measurements.json](data/ir_measurements.json) | Raw empirical IR reflectance measurements across live face, printed photo, and screen |
| [docs/George-Howdy-Liveness-2026.pdf](docs/George-Howdy-Liveness-2026.pdf) | Full research paper |
| [CITATION.cff](CITATION.cff) | Formal citation metadata |
| [LICENSE](LICENSE) | CC BY 4.0 |

---

## The Problem

Howdy authenticates using facial recognition but has no liveness detection. Any photograph or screen displaying the enrolled user's face will authenticate successfully. This is a known limitation affecting all Howdy installations on Linux.

Windows Hello addresses this using depth sensing and IR liveness analysis at the firmware level. No equivalent implementation exists for Linux.

---

## Approach

Consumer IR cameras emit infrared light in an alternating on/off flash cycle at approximately 60fps. Live skin and spoofing materials have measurably different IR reflectance signatures when analyzed across this cycle.

The spatial variance of the per-pixel IR on/off delta map is the primary discriminating feature:

| Material | Delta Mean | Spatial Variance | Ratio |
|----------|-----------|-----------------|-------|
| Live face | 14.14 | 150 | 1.0x (baseline) |
| Printed photo | 66.33 | 1,111 | 7.4x |
| Phone screen | 33.06 | 2,752 | 18.3x |

Live skin produces diffuse subsurface IR scattering with low spatial variance. Printed photos and screens produce specular reflection with high spatial variance. The discrimination is physically grounded — it reflects fundamental differences in how biological tissue vs. artificial surfaces interact with near-infrared light.

---

## Hardware

Tested on:
- Microsoft Surface Pro (2019), Surface Camera Front (045e:0990)
- Ubuntu 24.04 LTS
- Howdy 2.6.1
- Python 3.12, OpenCV 4.13, dlib 20.0

Compatible with any IR camera that uses alternating IR emitter flash cycling. Threshold calibration may be required for cameras with different IR emitter characteristics.

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
DELTA_MEAN_MAX = 40.0        # Live skin: ~14, Print: ~66, Screen: ~33
SPATIAL_VARIANCE_MAX = 400.0  # Live skin: ~150, Print: ~1,111, Screen: ~2,752
WARMUP_FRAMES = 10
SAMPLE_FRAMES = 60
```

Calibrate thresholds for your specific camera by running the diagnostic script before enrolling:

```bash
sudo python3 src/liveness.py
```

---

## Testing

```bash
# Test live face — expected output: LIVE
sudo python3 /lib/security/howdy/liveness.py

# Test with photo or screen — expected output: SPOOF DETECTED
sudo python3 /lib/security/howdy/liveness.py
```

Full PAM integration test:

```bash
sudo -k && sudo echo "PAM test"
```

---

## Empirical Data

Raw measurements in `data/ir_measurements.json`. Measurements taken on a single subject under indoor lighting conditions with a Microsoft Surface Pro IR camera. Multi-subject validation and cross-hardware characterization are identified as future work.

---

## Limitations

- Single-subject evaluation — thresholds may require calibration for different individuals and cameras
- 3D mask attacks not tested — thermal or structured-light depth sensing required for full protection
- Lighting conditions affect IR reflectance — validated under indoor conditions
- Requires IR camera with alternating emitter flash cycle — passive IR cameras without active illumination are not supported

---

## Future Work

- Blink detection challenge-response (in development)
- Multi-subject validation across hardware platforms
- Thermal camera integration for 3D mask detection
- Automated per-camera threshold calibration
- Cross-distribution packaging (Arch, Fedora)

---

## Related Work

- [Howdy](https://github.com/boltgolt/howdy) — Windows Hello-style facial authentication for Linux
- [Windows Hello](https://docs.microsoft.com/en-us/windows-hardware/design/device-experiences/windows-hello) — Microsoft biometric authentication framework
- [linux-surface](https://github.com/linux-surface/linux-surface) — Linux kernel support for Surface hardware

---

## Citation

**Vancouver**

George CB. Howdy liveness detection: passive IR reflectance analysis for anti-spoofing in Linux PAM facial authentication [Internet]. 2026. Available from: https://github.com/collingeorge/howdy-liveness

**APA**

George, C. B. (2026). *Howdy liveness detection: Passive IR reflectance analysis for anti-spoofing in Linux PAM facial authentication*. GitHub. https://github.com/collingeorge/howdy-liveness

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
