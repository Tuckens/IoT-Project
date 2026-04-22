"""Raspberry Pi Camera MJPEG streaming blueprint.

Streams the Pi camera feed as Motion-JPEG over HTTP so the dashboard
can display it in a standard <img> tag.

Requirements (on the Pi):
    sudo apt install -y python3-picamera2 python3-libcamera
"""

from flask import Blueprint, Response, jsonify
import io
import time
import threading
import atexit

from decorators import login_required

camera_bp = Blueprint('camera', __name__)

# ── Lazy singleton with a lock to prevent race conditions ──
_camera = None
_camera_available = None   # None = untested, True / False = cached result
_camera_lock = threading.Lock()


def _release_camera():
    """Called by atexit — cleanly release the camera so the next run can open it."""
    global _camera
    if _camera is not None:
        try:
            _camera.stop()
        except Exception:
            pass
        try:
            _camera.close()
        except Exception:
            pass
        _camera = None
        print("[camera] Camera released on shutdown.")


atexit.register(_release_camera)


def _get_camera():
    """Return a Picamera2 instance (created on first call). Returns None if unavailable."""
    global _camera, _camera_available

    # Fast path — already known
    if _camera_available is True:
        return _camera
    if _camera_available is False:
        return None

    with _camera_lock:
        # Double-check inside the lock (another thread may have set it already)
        if _camera_available is True:
            return _camera
        if _camera_available is False:
            return None

        # Try up to 2 times to open the camera (handles transient "Configured state" errors)
        for attempt in range(2):
            try:
                from picamera2 import Picamera2

                cam = Picamera2()
                cam.configure(
                    cam.create_video_configuration(
                        main={"size": (640, 480), "format": "RGB888"}
                    )
                )
                cam.start()
                time.sleep(1)  # warm-up

                _camera = cam
                _camera_available = True
                print("[camera] Camera initialised successfully.")
                return _camera

            except Exception as e:
                print(f"[camera] Init attempt {attempt + 1} failed: {e}")
                # Try to close whatever partial state exists
                try:
                    cam.close()
                except Exception:
                    pass
                if attempt == 0:
                    time.sleep(2)  # give libcamera time to reset

        _camera_available = False
        _camera = None
        print("[camera] Camera unavailable after 2 attempts.")
        return None


def _make_placeholder_frame():
    """Return a JPEG placeholder when the camera is unavailable."""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (640, 480), color=(20, 30, 45))
        draw = ImageDraw.Draw(img)
        draw.text((240, 225), "Camera offline", fill=(100, 140, 180))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()
    except Exception:
        # Hard-coded minimal valid 1×1 grey JPEG
        return (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
            b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
            b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\x1e\x00'
            b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00'
            b'\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00'
            b'\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00'
            b'\x08\x01\x01\x00\x00?\x00\xfb\xd4\x00\x00\x00\x1f\xff\xd9'
        )


def _generate_frames():
    """Yield MJPEG frames."""
    camera = _get_camera()
    if camera is None:
        frame = _make_placeholder_frame()
        while True:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
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
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.05)  # ~20 fps


@camera_bp.route('/stream')
@login_required
def video_stream():
    """MJPEG stream: /api/camera/stream"""
    return Response(
        _generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@camera_bp.route('/snapshot')
@login_required
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
@login_required
def status():
    """Camera availability probe: /api/camera/status"""
    _get_camera()  # trigger detection if not yet done
    return jsonify({"available": _camera_available is True})

