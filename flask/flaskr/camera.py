"""Raspberry Pi Camera MJPEG streaming blueprint.

Streams the Pi camera feed as Motion-JPEG over HTTP so the dashboard
can display it in a standard <img> tag.

Requirements (on the Pi):
    sudo apt install -y python3-picamera2 python3-libcamera
"""

from flask import Blueprint, Response, current_app
import io
import time

camera_bp = Blueprint('camera', __name__)

# ── Lazy singleton so the camera is only opened once ──
_camera = None


def _get_camera():
    """Return a Picamera2 instance, creating it on first call."""
    global _camera
    if _camera is None:
        from picamera2 import Picamera2
        _camera = Picamera2()
        _camera.configure(
            _camera.create_video_configuration(
                main={"size": (640, 480), "format": "RGB888"}
            )
        )
        _camera.start()
        time.sleep(1)  # warm-up
    return _camera


def _generate_frames():
    """Yield JPEG frames for the MJPEG stream."""
    camera = _get_camera()
    while True:
        buf = io.BytesIO()
        camera.capture_file(buf, format='jpeg')
        frame = buf.getvalue()
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
    buf = io.BytesIO()
    camera.capture_file(buf, format='jpeg')
    buf.seek(0)
    return Response(buf.getvalue(), mimetype='image/jpeg')
