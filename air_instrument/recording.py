from __future__ import annotations

import logging
import os
import time
import threading

import numpy as np
import scipy.io.wavfile as wavfile

logger = logging.getLogger(__name__)


class Recorder:
    """Manages audio event recording, WAV file export, and session playback."""

    def __init__(self) -> None:
        self.events: list[tuple[float, str, float]] = []
        self.start_t: float | None = None
        self.pause_t: float | None = None
        self.total_paused: float = 0.0
        self.is_recording: bool = False
        self.is_paused: bool = False
        self.is_playing_back: bool = False

    def start(self) -> None:
        """Starts a new recording session, clearing previous events."""
        self.events = []
        self.start_t = time.time()
        self.total_paused = 0.0
        self.is_recording = True
        self.is_paused = False

    def pause(self) -> None:
        """Pauses the active recording session."""
        if self.is_recording and not self.is_paused:
            self.pause_t = time.time()
            self.is_paused = True

    def resume(self) -> None:
        """Resumes a paused recording session."""
        if self.is_recording and self.is_paused:
            self.total_paused += time.time() - (self.pause_t or time.time())
            self.is_paused = False

    def stop(self, audio_engine: object = None) -> None:
        """Stops the recording session and exports the audio if an engine is provided."""
        self.is_recording = False
        self.is_paused = False
        if audio_engine:
            self.save_to_folder(audio_engine)

    def add_event(self, name: str, vol: float = 1.0) -> None:
        """Records a note trigger event with a relative timestamp and volume."""
        if self.is_recording and not self.is_paused:
            t = time.time() - (self.start_t or time.time()) - self.total_paused
            self.events.append((t, name, vol))

    def get_duration(self) -> float:
        """Returns the elapsed duration of the current recording session."""
        if not self.start_t:
            return 0.0
        if self.is_paused:
            return (self.pause_t or time.time()) - self.start_t - self.total_paused
        if self.is_recording:
            return time.time() - self.start_t - self.total_paused
        return self.events[-1][0] if self.events else 0.0

    def save_to_folder(self, audio_engine: object) -> None:
        """Saves recorded events as a compiled 16-bit WAV file in a background thread."""
        if not self.events:
            return

        _engine = audio_engine

        def save_thread() -> None:
            folder = "recordings"
            os.makedirs(folder, exist_ok=True)

            ts = time.strftime("%Y%m%d-%H%M%S")
            filename = os.path.join(folder, f"air_instrument_jam_{ts}.wav")

            max_t = self.get_duration()
            total_samples = int((max_t + 2.0) * _engine.sr)
            buffer = np.zeros(total_samples, dtype=np.float32)

            for t, name, vol in self.events:
                if name not in _engine.samples:
                    continue
                sample = _engine.samples[name] * vol
                start_idx = int(t * _engine.sr)
                end_idx = start_idx + len(sample)
                if start_idx >= total_samples:
                    continue
                write_end = min(end_idx, total_samples)
                take = write_end - start_idx
                if take > 0:
                    buffer[start_idx:write_end] += sample[:take]

            delay_samples = (
                len(_engine.delay_buffer)
                if hasattr(_engine, "delay_buffer")
                else int(_engine.sr * 0.4)
            )
            fb = getattr(_engine, "delay_feedback", 0.35)
            if delay_samples > 0 and len(buffer) > delay_samples:
                for p in range(4):
                    buffer[delay_samples:] += buffer[:-delay_samples] * (fb ** (p + 1))

            buffer = np.tanh(buffer * 1.5)
            int_buffer = np.int16(np.clip(buffer, -1.0, 1.0) * 32767)
            wavfile.write(filename, _engine.sr, int_buffer)
            logger.info("Saved performance to: %s", filename)

        threading.Thread(target=save_thread, daemon=True).start()

    def play_back(self, audio_engine: object) -> None:
        """Plays back recorded events in a background thread, preventing overlapping playback."""
        _engine = audio_engine

        def playback_thread() -> None:
            try:
                if not self.events:
                    return
                s_t = time.time()
                for t, name, vol in sorted(self.events, key=lambda x: x[0]):
                    while (time.time() - s_t) < t:
                        time.sleep(0.005)
                    _engine.play_sound(name, vol)
            finally:
                self.is_playing_back = False

        if not self.is_playing_back:
            self.is_playing_back = True
            threading.Thread(target=playback_thread, daemon=True).start()
