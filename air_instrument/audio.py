from __future__ import annotations

import logging
import os
import threading
from typing import Any

import numpy as np
import scipy.io.wavfile as wavfile
import sounddevice as sd

REQUIRED_SOUNDS: set[str] = {
    "kick",
    "snare",
    "hihat",
    "OPENHAT",
    "TOM_HI",
    "TOM_MID",
    "TOM_LOW",
    "CRASH",
    "RIDE",
    "C4",
    "D4",
    "E4",
    "F4",
    "G4",
    "A4",
    "B4",
}

logger = logging.getLogger(__name__)


class AudioEngine:
    def __init__(
        self, cfg: dict[str, Any] | None = None, sample_rate: int | None = None
    ) -> None:
        self.cfg = cfg or {}
        audio_cfg: dict[str, Any] = (
            self.cfg.get("audio") if isinstance(self.cfg, dict) else {}
        ) or {}
        self.sr: int = int(sample_rate or audio_cfg.get("sample_rate", 44100))
        self.active_samples: list[dict[str, Any]] = []
        delay_ms = int(audio_cfg.get("delay_ms", 400))
        self.delay_buffer: np.ndarray = np.zeros(
            int(self.sr * (delay_ms / 1000.0)), dtype=np.float32
        )
        self.delay_idx: int = 0
        self.delay_feedback: float = float(audio_cfg.get("delay_feedback", 0.35))

        self.samples: dict[str, np.ndarray] = {}
        self._lock = threading.Lock()
        self._load_all_assets()

        missing = REQUIRED_SOUNDS - set(self.samples.keys())
        if missing:
            logger.warning("Missing sounds: %s. Run setup_sounds.py first.", missing)
            raise RuntimeError(f"Missing sounds: {missing}. Run setup_sounds.py first.")

        preferred = [int(audio_cfg.get("blocksize", 256)), 512, 1024]
        for bs in preferred:
            try:
                self.stream = sd.OutputStream(
                    samplerate=self.sr,
                    channels=1,
                    callback=self._audio_callback,
                    blocksize=bs,
                    latency="low",
                )
                self.stream.start()
                logger.info("[Audio] blocksize=%d (%.1f ms)", bs, 1000 * bs / self.sr)
                break
            except Exception as e:
                logger.warning("Audio init failed for blocksize %d: %s", bs, e)
        else:
            logger.error("Failed to open audio output stream")
            raise RuntimeError("Audio Initialization Error: cannot open output stream")

    def _load_all_assets(self) -> None:
        folder = "sounds"
        if not os.path.exists(folder):
            logger.error("'%s' directory missing. Asset loading failed.", folder)
            return
        for file in os.listdir(folder):
            if not file.endswith(".wav"):
                continue
            try:
                sr, data = wavfile.read(os.path.join(folder, file))
                if data.dtype == np.int16:
                    data = data.astype(np.float32) / 32768.0
                if len(data.shape) > 1:
                    data = np.mean(data, axis=1)
                self.samples[file.replace(".wav", "")] = data
            except Exception as e:
                logger.warning("Failed to load %s: %s", file, e)

    def _audio_callback(
        self,
        outdata: np.ndarray,
        frames: int,
        time_info: object,
        status: object,
    ) -> None:
        with self._lock:
            samples_snapshot = list(self.active_samples)
        if status:
            logger.warning("Audio callback status: %s", status)

        chunk = np.zeros(frames, dtype=np.float32)
        still_active: list[dict[str, Any]] = []
        for s in samples_snapshot:
            data = s["data"]
            remaining = len(data) - s["ptr"]
            if remaining <= 0:
                continue
            take = min(frames, remaining)
            chunk[:take] += data[s["ptr"] : s["ptr"] + take] * s["vol"]
            s["ptr"] += take
            if s["ptr"] < len(data):
                still_active.append(s)

        with self._lock:
            newly_added = [x for x in self.active_samples if x not in samples_snapshot]
            self.active_samples = still_active + newly_added

        dbuf = self.delay_buffer
        db_len = len(dbuf)
        idx = self.delay_idx
        if idx + frames <= db_len:
            delayed = dbuf[idx : idx + frames].copy()
        else:
            first = db_len - idx
            delayed = np.empty(frames, dtype=np.float32)
            delayed[:first] = dbuf[idx:]
            delayed[first:] = dbuf[: frames - first]

        new_vals = chunk + delayed * self.delay_feedback
        if idx + frames <= db_len:
            dbuf[idx : idx + frames] = new_vals
        else:
            first = db_len - idx
            dbuf[idx:] = new_vals[:first]
            dbuf[: frames - first] = new_vals[first:]

        self.delay_idx = (idx + frames) % db_len
        chunk += delayed
        outdata[:, 0] = np.tanh(chunk * 1.5)

    def play_sound(
        self,
        name: str,
        vol: float = 1.0,
        stop_others: bool = False,
        stop_all: bool = False,
    ) -> None:
        if name not in self.samples:
            return
        with self._lock:
            if stop_all:
                self.active_samples = []
            elif stop_others:
                self.active_samples = [
                    s for s in self.active_samples if s["name"] != name
                ]
            self.active_samples.append(
                {
                    "name": name,
                    "data": self.samples[name],
                    "ptr": 0,
                    "vol": vol,
                }
            )

    def stop_all_notes(self) -> None:
        with self._lock:
            self.active_samples = []

    def close(self) -> None:
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass
