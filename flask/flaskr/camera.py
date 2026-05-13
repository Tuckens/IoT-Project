"""Raspberry Pi Camera MJPEG streaming blueprint.

The camera exposes two concurrent outputs:

- A permanent hardware-accelerated MJPEGEncoder that writes each JPEG
  frame into a thread-safe single-frame buffer (_StreamingOutput). The
  /api/camera/stream handler reads from that buffer, so it does zero
  Python-side JPEG encoding and never calls capture_file() in its hot
  path.
- An on-demand H264Encoder attached by recording.py while a clip is
  being written. Both encoders consume frames from the same camera
  stream but run in picamera2's own C threads, so they do not compete
  for the Python GIL.

Requirements (on the Pi):
    sudo apt install -y python3-picamera2 python3-libcamera ffmpeg
"""

from flask import Blueprint, Response, jsonify
import io
import logging
import time
import threading
import atexit

from .decorators import login_required

logger = logging.getLogger(__name__)
camera_bp = Blueprint('camera', __name__)

# ── Lazy singleton with a lock to prevent race conditions ──
_camera = None
_camera_available = None   # None = untested, True / False = cached result
_camera_lock = threading.Lock()
_mjpeg_encoder = None
_mjpeg_attached = False


class _StreamingOutput(io.BufferedIOBase):
    """Latest-frame buffer for MJPEG. picamera2's MJPEGEncoder writes each
    completed JPEG frame as a single ``write`` call; we overwrite the
    previous frame and notify waiters so consumers always see the freshest
    one."""

    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()
        return len(buf)


_streaming_output = _StreamingOutput()


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
                # YUV420 is the Pi camera's native format and what the
                # hardware JPEG/H264 encoders expect natively; it removes
                # an RGB conversion step and frees CPU cycles.
                cam.configure(
                    cam.create_video_configuration(
                        main={"size": (640, 480), "format": "YUV420"}
                    )
                )
                cam.start()
                time.sleep(1)  # warm-up

                _camera = cam
                _camera_available = True
                _attach_mjpeg_encoder(cam)
                logger.info("Camera initialised successfully.")
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


def _attach_mjpeg_encoder(cam) -> None:
    """Attach the permanent MJPEG encoder that drives /api/camera/stream.

    Idempotent: safe to call more than once (e.g. if the camera is closed
    and reopened). Failures fall back to the old capture_file() path via
    the frame generator below.
    """
    global _mjpeg_encoder, _mjpeg_attached
    if _mjpeg_attached:
        return
    try:
        from picamera2.encoders import MJPEGEncoder
        from picamera2.outputs import FileOutput
        # Bitrate is a quality target; the hardware JPEG encoder will
        # produce roughly this much data per second at 640x480@~20fps.
        _mjpeg_encoder = MJPEGEncoder(bitrate=4_000_000)
        cam.start_encoder(_mjpeg_encoder, FileOutput(_streaming_output), name="main")
        _mjpeg_attached = True
        logger.info("MJPEG encoder attached (hardware JPEG).")
    except Exception:
        logger.exception("failed to attach MJPEG encoder — falling back to capture_file")


MAX_CONSECUTIVE_ERRORS = 10


def _generate_frames():
    """Yield MJPEG frames from the shared _streaming_output buffer, so the
    hot path does zero Python-side encoding. Returns (closes the HTTP
    response) if the camera produces nothing for MAX_CONSECUTIVE_ERRORS
    consecutive attempts, letting the browser's <img onerror> reconnect
    instead of spinning forever."""
    camera = _get_camera()
    if camera is None:
        frame = _make_placeholder_frame()
        for _ in range(60):  # ~1 min of placeholder, then let the client retry
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(1)
        return

    # Fallback path: if MJPEGEncoder failed to attach (e.g. picamera2 too
    # old), use the original capture_file loop. Slower but still works.
    if not _mjpeg_attached:
        errors = 0
        while True:
            try:
                buf = io.BytesIO()
                camera.capture_file(buf, format='jpeg')
                frame = buf.getvalue()
                errors = 0
            except Exception:
                errors += 1
                logger.warning("capture_file error %d/%d", errors, MAX_CONSECUTIVE_ERRORS)
                if errors >= MAX_CONSECUTIVE_ERRORS:
                    return
                time.sleep(0.5)
                continue
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.05)
        return

    # Fast path: hardware-encoded MJPEG via the permanent encoder.
    errors = 0
    last_frame = None
    while True:
        with _streaming_output.condition:
            # wait() returns True on notify, False on timeout.
            got = _streaming_output.condition.wait(timeout=2.0)
            frame = _streaming_output.frame
        if not got or frame is None or frame is last_frame:
            errors += 1
            if errors >= MAX_CONSECUTIVE_ERRORS:
                logger.warning("MJPEG stream stalled — closing")
                return
            continue
        errors = 0
        last_frame = frame
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


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

