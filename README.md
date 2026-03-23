# Howdy Liveness Detection

IR-based anti-spoofing liveness detection for [Howdy](https://github.com/boltgolt/howdy) facial authentication on Linux.

## Overview

This module adds liveness detection to Howdy's PAM-integrated facial recognition, blocking photo, screen, and printed image spoofing attacks using passive IR reflectance analysis.

Developed and tested on Ubuntu 24.04 LTS with a Microsoft Surface Pro IR camera.

## The Problem

Howdy authenticates using facial recognition but has no liveness detection. A photograph or screen displaying the enrolled user's face will authenticate successfully. This implementation addresses that vulnerability.

## Approach

The Surface IR camera emits infrared light at ~60fps in an alternating on/off pattern. Live skin and spoofing materials have measurably different IR reflectance signatures:

| Material | Delta Mean | Spatial Variance |
|----------|-----------|-----------------|
| Live face | 14.14 | 150 |
| Printed photo | 66.33 | 1111 (7x) |
| Phone screen | 33.06 | 2752 (18x) |

The spatial variance of the per-pixel IR on/off delta map is the primary discriminating feature. Live skin produces diffuse subsurface IR scattering with low spatial variance. Printed photos and screens produce specular reflection with high spatial variance.

## Hardware

Tested on:
- Microsoft Surface Pro (2019), Surface Camera Front (045e:0990)
- Ubuntu 24.04 LTS
- Howdy 2.6.1

Compatible with any IR camera that uses alternating IR emitter flash cycling.

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

Apply the patches in `src/compare_patched.py` to your existing `/lib/security/howdy/compare.py`:

1. Add import after `from recorders.video_capture import VideoCapture`:
```python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from liveness import check_liveness
```

2. Add liveness check after `video_capture = VideoCapture(config)`:
```python
if not check_liveness(cap=video_capture.internal):
    sys.exit(14)
```

3. Add exit code 14 handler in `/lib/security/howdy/pam.py`:
```python
elif status == 14:
    syslog.syslog(syslog.LOG_WARNING, "Failure, liveness check failed - spoof attempt detected")
    syslog.closelog()
    pamh.conversation(pamh.Message(pamh.PAM_ERROR_MSG, "Liveness check failed"))
    return pamh.PAM_AUTH_ERR
```

## Configuration

Thresholds in `liveness.py`:
```python
DELTA_MEAN_MAX = 40.0       # Live skin: ~14, Print: ~66, Screen: ~33
SPATIAL_VARIANCE_MAX = 400.0 # Live skin: ~150, Print: ~1111, Screen: ~2752
```

Adjust if needed for your specific IR camera hardware.

## Testing
```bash
# Test live face
sudo python3 /lib/security/howdy/liveness.py

# Test with photo/screen
sudo python3 /lib/security/howdy/liveness.py
# Hold spoofing material in front of camera
```

Expected output: `LIVE` or `SPOOF DETECTED`

## Empirical Data

Raw measurements in `data/ir_measurements.json`.

## Limitations

- Single-subject evaluation (one enrolled user)
- 3D mask attacks not tested — thermal or depth sensing required for full protection
- Thresholds may require calibration for different IR camera hardware
- Lighting conditions affect IR reflectance — tested in indoor conditions

## Future Work

- Blink detection challenge-response (in development)
- Multi-subject validation
- Thermal camera integration for 3D mask detection
- Automated threshold calibration per camera

## Related Work

- [Howdy](https://github.com/boltgolt/howdy) — Windows Hello style facial authentication for Linux
- [Windows Hello](https://docs.microsoft.com/en-us/windows-hardware/design/device-experiences/windows-hello) — Microsoft's biometric authentication framework

## License

MIT

## Author

Collin George  
Independent Security Researcher  
Center for Competitive Statecraft and Strategic Policy
