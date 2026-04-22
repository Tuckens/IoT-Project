"""Motion- and temperature-triggered video recording.

Single active recording at a time. Priorities and transitions:

  - motion trigger starts a fixed-length (MOTION_DURATION) recording,
    and repeated motion extends it.
  - temperature trigger starts an open-ended recording while the current
    reading is strictly below the admin-configured threshold. When the
    reading rises to or above the threshold, the recording stops.
  - Only one recording runs at a time. If a temperature recording is
    already running, motion events are ignored (temperature is the
    higher priority). If a motion recording is running, a drop below
    the threshold is ignored until the motion clip finishes.

All filesystem paths are server-generated and filename-validated in db.py.
No caller ever passes a user-provided filename.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from datetime import datetime, timedelta

# Refuse to start a new recording below this many free bytes on the
# recordings volume — ffmpeg would otherwise produce a zero-byte file
# and leave an orphan DB row.
MIN_FREE_DISK_BYTES = 500 * 1024 * 1024  # 500 MB

from db import (
    RECORDINGS_DIR,
    create_recording_row,
    finalise_recording_row,
    get_setting,
)

logger = logging.getLogger(__name__)

MOTION_DURATION = timedelta(seconds=5)
# Hard cap so a misconfigured threshold cannot fill the SD card forever.
MAX_RECORDING_DURATION = timedelta(minutes=10)
TICK_INTERVAL_S = 0.5


def _filename(trigger: str, when: datetime) -> str:
    return f"{when.strftime('%Y%m%d-%H%M%S')}_{trigger}.mp4"


def _temperature_threshold():
    v = get_setting("temperature_alarm_below")
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class RecordingManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: dict | None = None
        self._stop_event = threading.Event()
        self._tick_thread = threading.Thread(
            target=self._tick_loop, name="recording-tick", daemon=True
        )
        self._tick_thread.start()

    # ── public surface ──

    def on_motion(self, detected: bool) -> None:
        if not detected:
            return
        now = datetime.now()
        with self._lock:
            if self._active is None:
                self._start_locked("motion", stop_at=now + MOTION_DURATION)
            elif self._active["trigger"] == "motion":
                self._active["stop_at"] = now + MOTION_DURATION

    def on_temperature(self, temp_c: float) -> None:
        threshold = _temperature_threshold()
        if threshold is None:
            return
        with self._lock:
            if temp_c < threshold:
                if self._active is None:
                    self._start_locked("temperature", stop_at=None)
            else:
                if self._active and self._active["trigger"] == "temperature":
                    self._stop_locked()

    def status(self) -> dict | None:
        with self._lock:
            if self._active is None:
                return None
            return {
                "trigger": self._active["trigger"],
                "filename": self._active["filename"],
                "started_at": self._active["started_at"].isoformat(),
                "ends_at": self._active["stop_at"].isoformat() if self._active.get("stop_at") else None,
            }

    # ── internals ──

    def _start_locked(self, trigger: str, stop_at: datetime | None) -> None:
        now = datetime.now()
        filename = _filename(trigger, now)
        path = os.path.join(RECORDINGS_DIR, filename)

        try:
            free = shutil.disk_usage(RECORDINGS_DIR).free
        except OSError:
            logger.exception("disk_usage failed; skipping free-space guard")
            free = None
        if free is not None and free < MIN_FREE_DISK_BYTES:
            logger.warning(
                "refusing to start %s recording: only %d MB free (< %d MB)",
                trigger, free // (1024 * 1024),
                MIN_FREE_DISK_BYTES // (1024 * 1024),
            )
            return

        try:
            from camera import _get_camera
            cam = _get_camera()
            if cam is None:
                logger.warning("cannot start %s recording: camera unavailable", trigger)
                return

            # picamera2 encoders are imported lazily so unit tests on a
            # non-Pi box do not need the library.
            from picamera2.encoders import H264Encoder
            from picamera2.outputs import FfmpegOutput

            encoder = H264Encoder(bitrate=3_000_000)
            output = FfmpegOutput(path)
            # start_encoder / stop_encoder only attach/detach the encoder.
            # We explicitly avoid start_recording / stop_recording: those
            # wrappers call cam.start()/cam.stop() which would tear down
            # the shared camera and the MJPEG encoder that feeds the live
            # stream. Instead we add a second encoder alongside the
            # permanent MJPEG one; picamera2 dispatches each frame to both.
            cam.start_encoder(encoder, output, name="main")
        except Exception:
            logger.exception("failed to start encoder")
            return

        try:
            rec_id = create_recording_row(filename, trigger)
        except Exception:
            logger.exception("failed to insert recording row; stopping encoder")
            try:
                cam.stop_encoder()
            except Exception:
                pass
            return

        hard_stop_at = now + MAX_RECORDING_DURATION
        effective_stop_at = stop_at if stop_at else hard_stop_at

        self._active = {
            "id": rec_id,
            "trigger": trigger,
            "filename": filename,
            "path": path,
            "started_at": now,
            "stop_at": effective_stop_at,
            "hard_stop_at": hard_stop_at,
            # Keep strong references so the encoder/ffmpeg output objects
            # are not garbage-collected while the recording is running.
            "_encoder_ref": encoder,
            "_output_ref": output,
        }
        logger.info("recording started: %s (%s)", filename, trigger)

    def _stop_locked(self) -> None:
        if not self._active:
            return
        active = self._active
        self._active = None  # release state early so re-entrant calls no-op

        try:
            from camera import _get_camera
            cam = _get_camera()
            if cam is not None:
                try:
                    # Target the H264 encoder only. Omitting the argument
                    # would stop every encoder, including the permanent
                    # MJPEG one that drives the live stream.
                    cam.stop_encoder(active["_encoder_ref"])
                except Exception:
                    logger.exception("cam.stop_encoder failed")
        except Exception:
            logger.exception("stop: camera import failed")

        try:
            size = os.path.getsize(active["path"]) if os.path.exists(active["path"]) else 0
        except OSError:
            size = 0
        duration = (datetime.now() - active["started_at"]).total_seconds()
        finalise_recording_row(active["id"], duration, size)
        logger.info(
            "recording stopped: %s (%.1fs, %d bytes)",
            active["filename"], duration, size,
        )

    def _tick_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception:
                logger.exception("recording tick failed")
            time.sleep(TICK_INTERVAL_S)

    def _tick(self) -> None:
        with self._lock:
            if not self._active:
                return
            now = datetime.now()
            # Hard ceiling first, so a mis-set threshold can't run forever.
            if now >= self._active.get("hard_stop_at", now):
                self._stop_locked()
                return
            stop_at = self._active.get("stop_at")
            if stop_at and now >= stop_at:
                self._stop_locked()


recording_manager = RecordingManager()
