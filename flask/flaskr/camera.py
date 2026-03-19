"""Raspberry Pi Camera MJPEG streaming blueprint.

Streams the Pi camera feed as Motion-JPEG over HTTP so the dashboard
can display it in a standard <img> tag.

Requirements (on the Pi):
    sudo apt install -y python3-picamera2 python3-libcamera
"""

from flask import Blueprint, Response, current_app, jsonify
import io
import time

camera_bp = Blueprint('camera', __name__)

# ── Lazy singleton so the camera is only opened once ──
_camera = None
_camera_available = None  # None = untested, True/False = result


def _get_camera():
    """Return a Picamera2 instance, creating it on first call. Returns None if unavailable."""
    global _camera, _camera_available
    if _camera_available is False:
        return None
    if _camera is None:
        try:
            from picamera2 import Picamera2
            _camera = Picamera2()
            _camera.configure(
                _camera.create_video_configuration(
                    main={"size": (640, 480), "format": "RGB888"}
                )
            )
            _camera.start()
            time.sleep(1)  # warm-up
            _camera_available = True
        except Exception as e:
            _camera_available = False
            _camera = None
            print(f"[camera] Camera unavailable: {e}")
    return _camera


def _make_placeholder_frame():
    """Return a minimal grey JPEG as a placeholder when the camera is unavailable."""
    try:
        from PIL import Image, ImageDraw
        import io as _io
        img = Image.new("RGB", (640, 480), color=(20, 30, 45))
        draw = ImageDraw.Draw(img)
        draw.text((220, 225), "Camera offline", fill=(100, 140, 180))
        buf = _io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()
    except Exception:
        # If Pillow is also missing, return a 1x1 grey JPEG (hard-coded minimal valid JPEG)
        return (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
            b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
            b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\x1e\x00'
            b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00'
            b'\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00'
            b'\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00'
            b'\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00'
            b'\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07"q\x142\x81'
            b'\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19'
            b'\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86'
            b'\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4'
            b'\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2'
            b'\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9'
            b'\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5'
            b'\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xd4'
            b'\x00\x00\x00\x1f\xff\xd9'
        )


def _generate_frames():
    """Yield JPEG frames for the MJPEG stream."""
    camera = _get_camera()
    if camera is None:
        # Stream placeholder frames at ~1 fps when camera is unavailable
        frame = _make_placeholder_frame()
        while True:
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
            )
            time.sleep(1)
    else:
        while True:
            try:
                buf = io.BytesIO()
                camera.capture_file(buf, format='jpeg')
                frame = buf.getvalue()
            except Exception as e:
                print(f"[camera] Frame capture error: {e}")
                time.sleep(0.5)
                continue
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
            )
            time.sleep(0.05)  # ~20 fps cap


@camera_bp.route('/stream')
def video_stream():
    """MJPEG stream endpoint: /api/camera/stream"""
    return Response(
        _generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@camera_bp.route('/snapshot')
def snapshot():
    """Single JPEG snapshot: /api/camera/snapshot"""
    camera = _get_camera()
    if camera is None:
        return Response(_make_placeholder_frame(), mimetype='image/jpeg')
    buf = io.BytesIO()
    camera.capture_file(buf, format='jpeg')
    buf.seek(0)
    return Response(buf.getvalue(), mimetype='image/jpeg')


@camera_bp.route('/status')
def status():
    """Return whether the Pi camera is available: /api/camera/status"""
    _get_camera()  # trigger detection if not yet done
    return jsonify({"available": _camera_available is True})

