from __future__ import annotations

import logging
import time
import threading
from typing import Any
from collections import deque

import cv2
import numpy as np

from air_instrument.config import load_config, setup_logging
from air_instrument.audio import AudioEngine
from air_instrument.recording import Recorder
from air_instrument.vision import HandTracker
from air_instrument.midi import MidiOut, DRUM_SOUNDS

logger = logging.getLogger(__name__)

# Modern UI Color Palette (BGR format)
COLOR_WHITE = (255, 255, 255)
COLOR_DARK_GRAY = (30, 30, 30)
COLOR_LIGHT_GRAY = (200, 200, 200)
COLOR_NEON_CYAN = (255, 255, 0)      # Cyan
COLOR_NEON_GREEN = (100, 255, 100)
COLOR_NEON_BLUE = (255, 120, 0)      # Neon Blue
COLOR_NEON_RED = (50, 50, 255)
COLOR_PANEL_BG = (15, 15, 15)
COLOR_BORDER = (80, 80, 80)

FINGER_LABELS = ["T", "I", "M", "R", "P"]
TIP_IDS = [4, 8, 12, 16, 20]

HAND_CONNECTIONS = [
    # Thumb
    (0, 1), (1, 2), (2, 3), (3, 4),
    # Index finger
    (0, 5), (5, 6), (6, 7), (7, 8),
    # Middle finger
    (9, 10), (10, 11), (11, 12),
    # Ring finger
    (13, 14), (14, 15), (15, 16),
    # Pinky
    (0, 17), (17, 18), (18, 19), (19, 20),
    # Palm base connections
    (5, 9), (9, 13), (13, 17)
]


class AirInstrument:
    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self.cfg = cfg or load_config()
        logger.info("Initializing Air Instrument Audio & Recording Subsystem...")
        self.audio = AudioEngine(cfg=self.cfg)
        self.recorder = Recorder()
        self.tracker = HandTracker(cfg=self.cfg)
        self.midi = MidiOut(cfg=self.cfg.get("midi", {}))

        # Active note tracking for MIDI note_off to avoid hung notes.
        # Format: hand_idx -> set of playing sound_names
        self.active_hand_midi_notes: dict[int, set[str]] = {0: set(), 1: set()}
        self.active_combo_midi_notes: set[str] = set()

        # Percussive note-off queue: (sound_name, trigger_time)
        self.percussive_midi_queue: list[tuple[str, float]] = []

        # Hand position history for speed/velocity tracking
        # hand_idx -> deque of (timestamp, cx, cy)
        self.hand_pos_history: dict[int, deque[tuple[float, int, int]]] = {
            0: deque(maxlen=5),
            1: deque(maxlen=5),
        }

        # Track last CC values for HUD display
        self.last_hud_cc_values: dict[str, int] = {"MOD": 0, "PAN": 64, "CUTOFF": 0}
        self.last_trigger_velocity: int = 100

        cam_idx = int(self.cfg.get("camera", {}).get("device_index", 0))
        self.cap = cv2.VideoCapture(cam_idx)
        if not self.cap.isOpened():
            logger.error(
                "Camera index %s not available. Update config camera.device_index.",
                cam_idx,
            )
            raise RuntimeError(f"Camera index {cam_idx} not available.")

        self._set_camera_props()

        self.mode: str = "PIANO"
        self.modes: list[str] = ["PIANO", "DRUMS", "COMBO"]

        self.piano_mapping: dict[str, str] = {
            "POINTER": "C4",
            "PEACE": "D4",
            "THREE": "E4",
            "FOUR": "F4",
            "OPEN": "G4",
            "ROCK": "A4",
            "SHAKA": "B4",
        }
        self.drum_mapping: dict[str, str] = {
            "FIST": "kick",
            "POINTER": "snare",
            "PEACE": "hihat",
            "THREE": "TOM_HI",
            "FOUR": "TOM_MID",
            "OPEN": "OPENHAT",
            "ROCK": "CRASH",
            "SHAKA": "RIDE",
        }
        self.combo_single: dict[str, str] = {
            "FIST": "kick",
            "POINTER": "D4",
            "PEACE": "snare",
            "ROCK": "CRASH",
            "SHAKA": "RIDE",
            "THREE": "E4",
            "FOUR": "F4",
            "OPEN": "hihat",
        }
        self.combo_two_hand: dict[str, str] = {
            "0+1": "C4",
            "1+2": "G4",
            "2+3": "A4",
            "3+4": "B4",
            "0+5": "TOM_LOW",
            "1+5": "TOM_MID",
            "2+5": "TOM_HI",
            "0+2": "OPENHAT",
        }

        self.last_gestures: list[str] = ["UNKNOWN", "UNKNOWN"]
        self.last_combo: str = "NONE"
        self.last_trigger_times: list[float] = [0.0, 0.0]
        self.visual_fx: list[dict[str, Any]] = []

        confirm_frames = int(self.cfg.get("gesture", {}).get("confirm_frames", 3))
        self.gesture_buffer: list[deque] = [
            deque(maxlen=confirm_frames) for _ in range(2)
        ]
        self.combo_buffer: deque = deque(maxlen=confirm_frames)

        self.last_hand_count: int = 0
        self.fps: float = 0.0
        self.calib_msg: str = ""
        self.calibrating: bool = False
        self.calib_start: float = 0.0
        self.calib_samples: list[Any] = []

    def _set_camera_props(self) -> None:
        cam_cfg = self.cfg.get("camera", {})
        w = int(cam_cfg.get("width", 1280))
        h = int(cam_cfg.get("height", 720))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        self.w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or w
        self.h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or h

    def draw_panel(self, img: np.ndarray, pt1: tuple[int, int], pt2: tuple[int, int], color: tuple[int, int, int], alpha: float) -> None:
        overlay = img.copy()
        cv2.rectangle(overlay, pt1, pt2, color, -1)
        cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)

    def draw_hud(self, frame: np.ndarray) -> None:
        # Draw sleek top bar panel
        self.draw_panel(frame, (0, 0), (self.w, 60), COLOR_PANEL_BG, 0.75)
        cv2.line(frame, (0, 60), (self.w, 60), COLOR_BORDER, 1)

        # Title
        cv2.putText(
            frame,
            "AIR INSTRUMENT & MIDI CONTROLLER",
            (20, 38),
            cv2.FONT_HERSHEY_PLAIN,
            1.5,
            COLOR_NEON_CYAN,
            2,
        )

        # Mode indicator on right of top bar
        modes = ["PIANO", "DRUMS", "COMBO"]
        x_mode = self.w - 420
        for m in modes:
            if m == self.mode:
                cv2.rectangle(frame, (x_mode - 8, 16), (x_mode + 88, 44), COLOR_NEON_GREEN, 1)
                cv2.putText(
                    frame,
                    m,
                    (x_mode, 36),
                    cv2.FONT_HERSHEY_PLAIN,
                    1.1,
                    COLOR_NEON_GREEN,
                    2,
                )
            else:
                cv2.putText(
                    frame,
                    m,
                    (x_mode, 36),
                    cv2.FONT_HERSHEY_PLAIN,
                    1.1,
                    COLOR_BORDER,
                    1,
                )
            x_mode += 130

        # Draw sleek bottom bar panel
        self.draw_panel(frame, (0, self.h - 50), (self.w, self.h), COLOR_PANEL_BG, 0.75)
        cv2.line(frame, (0, self.h - 50), (self.w, self.h - 50), COLOR_BORDER, 1)

        # Recording Status
        if self.recorder.is_recording:
            rec_text = f"REC: {self.recorder.get_duration():.1f}s"
            rec_color = COLOR_NEON_RED if int(time.time() * 2) % 2 == 0 else COLOR_WHITE
            if self.recorder.is_paused:
                rec_text = f"PAUSED: {self.recorder.get_duration():.1f}s"
                rec_color = COLOR_NEON_CYAN
        else:
            rec_text = "REC: OFF"
            rec_color = COLOR_LIGHT_GRAY

        cv2.putText(
            frame,
            rec_text,
            (20, self.h - 18),
            cv2.FONT_HERSHEY_PLAIN,
            1.3,
            rec_color,
            2,
        )

        # Control keyboard shortcuts helper
        shortcuts = "[M] Mode  [R] Record  [P] Pause  [SPACE] Playback  [Q] Quit"
        cv2.putText(
            frame,
            shortcuts,
            (self.w - 580, self.h - 18),
            cv2.FONT_HERSHEY_PLAIN,
            1.1,
            COLOR_WHITE,
            1,
        )

        # Active Notes Status Panel (Left Floating Panel)
        self.draw_panel(frame, (20, 80), (280, 230), COLOR_PANEL_BG, 0.6)
        cv2.rectangle(frame, (20, 80), (280, 230), COLOR_BORDER, 1)
        cv2.putText(frame, "ACTIVE NOTES", (35, 105), cv2.FONT_HERSHEY_PLAIN, 1.2, COLOR_WHITE, 2)

        # Left hand active note
        lh_gest = self.last_gestures[0] if len(self.last_gestures) > 0 else "UNKNOWN"
        lh_note = list(self.active_hand_midi_notes.get(0, set()))
        lh_text = f"L: {lh_gest} -> {lh_note[0] if lh_note else 'None'}"
        cv2.putText(frame, lh_text, (35, 140), cv2.FONT_HERSHEY_PLAIN, 1.0, COLOR_NEON_BLUE, 1)

        # Right hand active note
        rh_gest = self.last_gestures[1] if len(self.last_gestures) > 1 else "UNKNOWN"
        rh_note = list(self.active_hand_midi_notes.get(1, set()))
        rh_text = f"R: {rh_gest} -> {rh_note[0] if rh_note else 'None'}"
        cv2.putText(frame, rh_text, (35, 175), cv2.FONT_HERSHEY_PLAIN, 1.0, COLOR_NEON_BLUE, 1)

        # Combo note if any
        if self.mode == "COMBO" and self.last_combo != "NONE":
            combo_note = list(self.active_combo_midi_notes)
            combo_text = f"COMBO: {self.last_combo} -> {combo_note[0] if combo_note else 'None'}"
            cv2.putText(frame, combo_text, (35, 205), cv2.FONT_HERSHEY_PLAIN, 1.0, COLOR_NEON_GREEN, 1)

        # Call System Monitor panel
        self._draw_debug_panel(frame)

    def _draw_debug_panel(self, frame: np.ndarray) -> None:
        # Draw translucent debug background on right side
        self.draw_panel(frame, (self.w - 340, 80), (self.w - 20, 310), COLOR_PANEL_BG, 0.6)
        cv2.rectangle(frame, (self.w - 340, 80), (self.w - 20, 310), COLOR_BORDER, 1)

        cv2.putText(frame, "SYSTEM MONITOR", (self.w - 325, 105), cv2.FONT_HERSHEY_PLAIN, 1.2, COLOR_WHITE, 2)
        
        # FPS and Hands
        cv2.putText(frame, f"FPS: {self.fps:.1f}  |  Hands: {self.last_hand_count}", (self.w - 325, 135), cv2.FONT_HERSHEY_PLAIN, 1.0, COLOR_LIGHT_GRAY, 1)
        
        # MIDI Port
        port_str = self.midi.active_port_name if self.midi.enabled else "DISABLED"
        if len(port_str) > 22:
            port_str = port_str[:20] + "..."
        cv2.putText(frame, f"Port: {port_str}", (self.w - 325, 160), cv2.FONT_HERSHEY_PLAIN, 1.0, COLOR_LIGHT_GRAY, 1)
        
        # Last velocity
        cv2.putText(frame, f"Last Velocity: {self.last_trigger_velocity}", (self.w - 325, 185), cv2.FONT_HERSHEY_PLAIN, 1.0, COLOR_LIGHT_GRAY, 1)

        # Expression CC Channels
        cc_y = 210
        for label, val in [("MOD Wheel (CC1)", "MOD"), ("Stereo Pan (CC10)", "PAN"), ("Filter Cut (CC74)", "CUTOFF")]:
            v = self.last_hud_cc_values.get(val, 0)
            cv2.putText(frame, f"{label}: {v:3d}", (self.w - 325, cc_y), cv2.FONT_HERSHEY_PLAIN, 0.9, COLOR_NEON_CYAN, 1)
            # Draw CC visual progress bar
            cv2.rectangle(frame, (self.w - 170, cc_y - 8), (self.w - 35, cc_y), (50, 50, 50), -1)
            fill_w = int((v / 127.0) * 135)
            cv2.rectangle(frame, (self.w - 170, cc_y - 8), (self.w - 170 + fill_w, cc_y), COLOR_NEON_CYAN, -1)
            cc_y += 22

        # Calibration
        calib_str = self.calib_msg if self.calib_msg else "Calib: READY [c]"
        if len(calib_str) > 28:
            calib_str = calib_str[:26] + "..."
        cv2.putText(frame, calib_str, (self.w - 325, 295), cv2.FONT_HERSHEY_PLAIN, 1.0, COLOR_NEON_GREEN, 1)

    def process_frame_logic(self, frame: np.ndarray, results: Any) -> None:
        # Process percussive MIDI note offs (auto-off after 100ms)
        now = time.time()
        still_pending = []
        for sound_name, trigger_time in self.percussive_midi_queue:
            if now - trigger_time >= 0.1:
                self.midi.note_off(sound_name)
            else:
                still_pending.append((sound_name, trigger_time))
        self.percussive_midi_queue = still_pending

        hand_data: list[dict[str, Any]] = []
        self.last_hand_count = (
            len(results.hand_landmarks) if results.hand_landmarks else 0
        )

        if results.hand_landmarks:
            for hand_idx, hand_landmarks in enumerate(results.hand_landmarks):
                fingers_count, fingers_states = self.tracker.count_fingers(
                    hand_landmarks
                )
                gest = self.tracker.detect_gesture(hand_landmarks, fingers_states)

                cx = int(hand_landmarks[9].x * self.w)
                cy = int(hand_landmarks[9].y * self.h)

                # Track hand positions for velocity/speed
                self.hand_pos_history[hand_idx].append((now, cx, cy))

                # Send continuous CC expression based on primary hand position
                self._send_midi_cc_expression(hand_idx, cx, cy, hand_landmarks)

                tips_px = [
                    (
                        int(hand_landmarks[tid].x * self.w),
                        int(hand_landmarks[tid].y * self.h),
                    )
                    for tid in TIP_IDS
                ]

                # Draw skeleton connection lines
                for p1_idx, p2_idx in HAND_CONNECTIONS:
                    try:
                        pt1 = hand_landmarks[p1_idx]
                        pt2 = hand_landmarks[p2_idx]
                        x1, y1 = int(pt1.x * self.w), int(pt1.y * self.h)
                        x2, y2 = int(pt2.x * self.w), int(pt2.y * self.h)
                        cv2.line(frame, (x1, y1), (x2, y2), COLOR_WHITE, 1)
                    except Exception:
                        pass

                # Draw joint dots
                for lm_idx, lm in enumerate(hand_landmarks):
                    x, y = int(lm.x * self.w), int(lm.y * self.h)
                    if lm_idx in TIP_IDS:
                        finger_idx = TIP_IDS.index(lm_idx)
                        state = fingers_states[finger_idx]
                        col = COLOR_NEON_GREEN if state else COLOR_NEON_RED
                        cv2.circle(frame, (x, y), 8, col, -1)
                        cv2.putText(
                            frame,
                            FINGER_LABELS[finger_idx],
                            (x + 12, y + 6),
                            cv2.FONT_HERSHEY_PLAIN,
                            1.0,
                            COLOR_WHITE,
                            1,
                        )
                    else:
                        cv2.circle(frame, (x, y), 4, COLOR_NEON_BLUE, -1)

                # Draw hand center target reticle and active gesture tag
                cv2.circle(frame, (cx, cy), 12, COLOR_NEON_CYAN, 2)
                cv2.line(frame, (cx - 20, cy), (cx + 20, cy), COLOR_NEON_CYAN, 1)
                cv2.line(frame, (cx, cy - 20), (cx, cy + 20), COLOR_NEON_CYAN, 1)
                
                cv2.putText(
                    frame,
                    f"G: {gest} ({fingers_count})",
                    (cx + 20, cy - 20),
                    cv2.FONT_HERSHEY_PLAIN,
                    1.2,
                    COLOR_NEON_CYAN,
                    2,
                )

                hand_data.append(
                    {
                        "idx": hand_idx,
                        "gest": gest,
                        "fingers": fingers_count,
                        "states": fingers_states,
                        "tips": tips_px,
                        "cx": cx,
                        "cy": cy,
                    }
                )

                while hand_idx >= len(self.last_gestures):
                    self.last_gestures.append("UNKNOWN")
                    self.last_trigger_times.append(0.0)

        active_indices = {hd["idx"] for hd in hand_data}
        for i in range(len(self.last_gestures)):
            if i not in active_indices:
                if self.last_gestures[i] != "UNKNOWN":
                    logger.debug("Hand %d lost - clearing last gesture and notes", i)
                    self._clear_all_hand_midi_notes(i)
                self.last_gestures[i] = "UNKNOWN"
                try:
                    self.gesture_buffer[i].clear()
                except Exception:
                    pass
                if i in self.hand_pos_history:
                    self.hand_pos_history[i].clear()

        combo_triggered = False

        if self.mode == "COMBO":
            combo_triggered = self._process_combo_mode(hand_data, now)

        if not combo_triggered and self.mode != "COMBO":
            self._process_single_mode(hand_data, now)

        self._draw_visual_fx(frame)

    def _midi_note_on(self, sound_name: str, hand_idx: int | None = None, is_combo: bool = False) -> None:
        """Triggers a MIDI note, tracking it to prevent hung notes and using dynamic velocity if configured."""
        velocity = 100
        midi_cfg = self.cfg.get("midi", {})
        
        # Calculate dynamic velocity if enabled
        if midi_cfg.get("velocity", {}).get("mode", "dynamic") == "dynamic" and hand_idx is not None:
            velocity = self._calculate_hand_velocity(hand_idx)
        else:
            velocity = int(midi_cfg.get("velocity", {}).get("default_value", 100))
            
        self.last_trigger_velocity = velocity
        
        # Send MIDI note on
        self.midi.note_on(sound_name, velocity=velocity)
        
        # Track the note
        if sound_name in DRUM_SOUNDS:
            # Percussive sounds get scheduled for auto-off
            self.percussive_midi_queue.append((sound_name, time.time()))
        else:
            # Pitched sounds are tracked by hand/combo
            if is_combo:
                self.active_combo_midi_notes.add(sound_name)
            elif hand_idx is not None:
                self.active_hand_midi_notes[hand_idx].add(sound_name)

    def _midi_note_off(self, sound_name: str, hand_idx: int | None = None, is_combo: bool = False) -> None:
        """Sends a MIDI note off message and untracks the note."""
        self.midi.note_off(sound_name)
        if is_combo:
            self.active_combo_midi_notes.discard(sound_name)
        elif hand_idx is not None:
            if hand_idx in self.active_hand_midi_notes:
                self.active_hand_midi_notes[hand_idx].discard(sound_name)

    def _clear_all_hand_midi_notes(self, hand_idx: int) -> None:
        """Clears all active notes triggered by a specific hand."""
        if hand_idx in self.active_hand_midi_notes:
            for sound_name in list(self.active_hand_midi_notes[hand_idx]):
                self._midi_note_off(sound_name, hand_idx=hand_idx)

    def _clear_all_combo_midi_notes(self) -> None:
        """Clears all active combo notes."""
        for sound_name in list(self.active_combo_midi_notes):
            self._midi_note_off(sound_name, is_combo=True)

    def _calculate_hand_velocity(self, hand_idx: int) -> int:
        """Calculates MIDI velocity based on the movement speed of the hand."""
        history = self.hand_pos_history.get(hand_idx)
        if not history or len(history) < 2:
            return 100  # Fallback default
            
        total_dist = 0.0
        total_dt = 0.0
        hist_list = list(history)
        
        for i in range(len(hist_list) - 1):
            t1, x1, y1 = hist_list[i]
            t2, x2, y2 = hist_list[i+1]
            dt = t2 - t1
            if dt <= 0:
                continue
            dist = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
            total_dist += dist
            total_dt += dt
            
        if total_dt <= 0:
            return 100
            
        speed = total_dist / total_dt  # Pixels per second
        
        min_vel, max_vel = 40, 127
        max_speed = 1800.0  # Pixels/sec considered maximum hit speed
        
        if speed > max_speed:
            speed = max_speed
            
        velocity = int(min_vel + (speed / max_speed) * (max_vel - min_vel))
        return velocity

    def _send_midi_cc_expression(self, hand_idx: int, cx: int, cy: int, hand_landmarks: Any) -> None:
        """Calculates and sends continuous MIDI CC messages based on hand coordinates."""
        # Only process for the primary hand (hand 0) to avoid CC conflicts in single channel setup
        if hand_idx != 0:
            return
            
        midi_cfg = self.cfg.get("midi", {})
        expr_cfg = midi_cfg.get("expression", {})
        if not expr_cfg.get("enabled", False):
            return
            
        channel = int(midi_cfg.get("channel", 0))
        
        # 1. Y Axis CC (e.g. Modulation Wheel)
        y_opt = expr_cfg.get("y_axis", {})
        if y_opt:
            cc_num = int(y_opt.get("cc_number", 1))
            val_min = int(y_opt.get("min_value", 0))
            val_max = int(y_opt.get("max_value", 127))
            invert = bool(y_opt.get("invert", True))
            
            norm_y = cy / self.h
            if invert:
                norm_y = 1.0 - norm_y
                
            cc_val = int(val_min + norm_y * (val_max - val_min))
            cc_val = max(0, min(127, cc_val))
            self.midi.control_change(cc_num, cc_val, channel=channel)
            self.last_hud_cc_values["MOD"] = cc_val

        # 2. X Axis CC (e.g. Pan)
        x_opt = expr_cfg.get("x_axis", {})
        if x_opt:
            cc_num = int(x_opt.get("cc_number", 10))
            val_min = int(x_opt.get("min_value", 0))
            val_max = int(x_opt.get("max_value", 127))
            invert = bool(x_opt.get("invert", False))
            
            norm_x = cx / self.w
            if invert:
                norm_x = 1.0 - norm_x
                
            cc_val = int(val_min + norm_x * (val_max - val_min))
            cc_val = max(0, min(127, cc_val))
            self.midi.control_change(cc_num, cc_val, channel=channel)
            self.last_hud_cc_values["PAN"] = cc_val

        # 3. Z Axis CC (Depth via palm size)
        z_opt = expr_cfg.get("z_axis", {})
        if z_opt:
            cc_num = int(z_opt.get("cc_number", 74))
            val_min = int(z_opt.get("min_value", 0))
            val_max = int(z_opt.get("max_value", 127))
            invert = bool(z_opt.get("invert", False))
            
            try:
                pt0 = hand_landmarks[0]
                pt9 = hand_landmarks[9]
                x0, y0 = pt0.x * self.w, pt0.y * self.h
                x9, y9 = pt9.x * self.w, pt9.y * self.h
                palm_size = np.sqrt((x9 - x0)**2 + (y9 - y0)**2)
            except Exception:
                palm_size = 100.0
                
            min_palm, max_palm = 40.0, 240.0
            norm_z = (palm_size - min_palm) / (max_palm - min_palm)
            norm_z = max(0.0, min(1.0, norm_z))
            if invert:
                norm_z = 1.0 - norm_z
                
            cc_val = int(val_min + norm_z * (val_max - val_min))
            cc_val = max(0, min(127, cc_val))
            self.midi.control_change(cc_num, cc_val, channel=channel)
            self.last_hud_cc_values["CUTOFF"] = cc_val

    def _process_combo_mode(self, hand_data: list[dict[str, Any]], now: float) -> bool:
        combo_triggered = False

        if len(hand_data) == 2:
            f1, f2 = hand_data[0]["fingers"], hand_data[1]["fingers"]
            combo_key = f"{min(f1, f2)}+{max(f1, f2)}"
            self.combo_buffer.append(combo_key)

            if len(self.combo_buffer) == self.combo_buffer.maxlen and all(
                x == self.combo_buffer[-1] for x in self.combo_buffer
            ):
                confirmed = self.combo_buffer[-1]
                if confirmed in self.combo_two_hand and confirmed != self.last_combo:
                    # Clear individual notes before entering combo
                    self._clear_all_hand_midi_notes(0)
                    self._clear_all_hand_midi_notes(1)
                    self._clear_all_combo_midi_notes()

                    snd = self.combo_two_hand[confirmed]
                    self.audio.play_sound(snd, vol=0.9)
                    self.recorder.add_event(snd)
                    mx = (hand_data[0]["cx"] + hand_data[1]["cx"]) // 2
                    my = (hand_data[0]["cy"] + hand_data[1]["cy"]) // 2
                    self.visual_fx.append(
                        {"x": mx, "y": my, "r": 30, "txt": f"COMBO: {snd}", "life": 1.0}
                    )
                    logger.debug("Combo triggered: %s", snd)
                    
                    self._midi_note_on(snd, is_combo=True)
                    self.last_combo = confirmed
                    combo_triggered = True
        else:
            self.combo_buffer.clear()
            if self.last_combo != "NONE":
                self._clear_all_combo_midi_notes()
            self.last_combo = "NONE"

        if not combo_triggered:
            for hd in hand_data:
                idx = hd["idx"]
                buf = self.gesture_buffer[idx]
                buf.append(hd["gest"])
                if len(buf) == buf.maxlen and all(x == buf[-1] for x in buf):
                    confirmed = buf[-1]
                    if confirmed != self.last_gestures[idx]:
                        # Turn off previous note for this hand
                        self._clear_all_hand_midi_notes(idx)
                        
                        if confirmed in self.combo_single:
                            snd = self.combo_single[confirmed]
                            self.audio.play_sound(snd, vol=0.8)
                            self.recorder.add_event(snd)
                            self.visual_fx.append(
                                {
                                    "x": hd["cx"],
                                    "y": hd["cy"],
                                    "r": 20,
                                    "txt": snd,
                                    "life": 1.0,
                                }
                            )
                            logger.debug("Combo single triggered: %s hand=%d", snd, idx)
                            self._midi_note_on(snd, hand_idx=idx)
                            self.last_gestures[idx] = confirmed
                        else:
                            self.last_gestures[idx] = confirmed

        return combo_triggered

    def _process_single_mode(self, hand_data: list[dict[str, Any]], now: float) -> None:
        mapping: dict[str, str] = (
            self.piano_mapping if self.mode == "PIANO" else self.drum_mapping
        )
        stop_others = self.mode == "PIANO"
        vol = 0.8 if self.mode == "PIANO" else 0.9

        for hd in hand_data:
            idx = hd["idx"]
            buf = self.gesture_buffer[idx]
            buf.append(hd["gest"])
            if len(buf) == buf.maxlen and all(x == buf[-1] for x in buf):
                confirmed = buf[-1]
                if confirmed != self.last_gestures[idx]:
                    # Turn off previous note for this hand
                    self._clear_all_hand_midi_notes(idx)
                    
                    if confirmed in mapping:
                        snd = mapping[confirmed]
                        self.audio.play_sound(snd, vol=vol, stop_others=stop_others)
                        self.recorder.add_event(snd)
                        self.visual_fx.append(
                            {
                                "x": hd["cx"],
                                "y": hd["cy"],
                                "r": 20,
                                "txt": snd,
                                "life": 1.0,
                            }
                        )
                        logger.debug(
                            "%s triggered: %s hand=%d",
                            self.mode,
                            snd,
                            idx,
                        )
                        self._midi_note_on(snd, hand_idx=idx)
                        self.last_gestures[idx] = confirmed
                        if self.mode == "DRUMS":
                            self.last_trigger_times[idx] = now
                    else:
                        self.last_gestures[idx] = confirmed

    def _draw_visual_fx(self, frame: np.ndarray) -> None:
        active: list[dict[str, Any]] = []
        for fx in self.visual_fx:
            if fx["life"] <= 0:
                continue
            cv2.circle(
                frame,
                (fx["x"], fx["y"]),
                int(fx["r"]),
                COLOR_NEON_GREEN,
                max(1, int(3 * fx["life"])),
            )
            cv2.putText(
                frame,
                fx["txt"],
                (fx["x"] + 30, fx["y"]),
                cv2.FONT_HERSHEY_PLAIN,
                1.5 + fx["life"],
                COLOR_NEON_GREEN,
                2,
            )
            fx["r"] += 15
            fx["life"] -= 0.1
            active.append(fx)
        self.visual_fx = active

    def run(self) -> None:
        logger.info("Air MIDI Instrument & Controller System initialized")
        logger.info("Booting...")

        debug = (
            bool(self.cfg.get("debug", False))
            or str(self.cfg.get("logging", {}).get("level", "")).upper() == "DEBUG"
        )
        if debug:
            logger.debug("entering main loop")

        frame_times: deque[float] = deque(maxlen=64)
        self.fps = 0.0
        self.calib_msg = ""
        self.calibrating = False
        self.calib_start = 0.0
        self.calib_duration = int(
            self.cfg.get("gesture", {}).get("calib_duration_s", 3)
        )
        self.calib_multiplier = float(
            self.cfg.get("gesture", {}).get("calib_multiplier", 0.5)
        )
        self.calib_samples = []

        while self.cap.isOpened():
            success, raw_frame = self.cap.read()
            if debug:
                logger.debug("cap.read success=%s", success)
            if not success:
                break

            raw_frame = cv2.flip(raw_frame, 1)
            try:
                results = self.tracker.get_landmarks(raw_frame)
            except Exception as e:
                if debug:
                    logger.debug("tracker.get_landmarks error: %s", e)
                break

            frame_times.append(time.time())
            if len(frame_times) >= 2:
                span = frame_times[-1] - frame_times[0]
                self.fps = len(frame_times) / (span + 1e-9)

            frame = raw_frame.copy()

            if self.calibrating:
                self._update_calibration(results)

            self.draw_hud(frame)
            self.process_frame_logic(frame, results)

            cv2.imshow("Air Instrument Controller", frame)

            # Allow clean exit if window is closed by the user
            if cv2.getWindowProperty("Air Instrument Controller", cv2.WND_PROP_VISIBLE) < 1:
                break

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("c"):
                self._handle_calibration_key(results)
            elif key == ord("m"):
                self._handle_mode_switch()
            elif key == ord("r"):
                if self.recorder.is_recording:
                    self.recorder.stop(self.audio)
                else:
                    self.recorder.start()
            elif key == ord("p"):
                if self.recorder.is_paused:
                    self.recorder.resume()
                else:
                    self.recorder.pause()
            elif key == ord(" "):
                self.recorder.play_back(self.audio)

        self.cleanup()

    def _update_calibration(self, results: Any) -> None:
        elapsed = time.time() - self.calib_start
        remaining = max(0, int(self.calib_duration - elapsed))
        if results.hand_landmarks:
            for hl in results.hand_landmarks:
                self.calib_samples.append(hl)
        self.calib_msg = f"Calibrating: {remaining}s"

        if elapsed >= self.calib_duration:
            if self.calib_samples:
                t, f = self.tracker.calibrate_from_landmarks(
                    self.calib_samples, multiplier=self.calib_multiplier
                )
                self.calib_msg = (
                    f"Calibrated: T={t:.3f} F={f:.3f} (m={self.calib_multiplier})"
                )
            else:
                self.calib_msg = "Calibration failed: no hands seen"
            self.calibrating = False
            self.calib_samples = []

            def _clear_msg(p: str) -> None:
                time.sleep(4)
                if getattr(self, "calib_msg", "") == p:
                    self.calib_msg = ""

            threading.Thread(
                target=_clear_msg, args=(self.calib_msg,), daemon=True
            ).start()

    def _handle_calibration_key(self, results: Any) -> None:
        if results.hand_landmarks:
            t, f = self.tracker.calibrate_from_landmarks(
                results.hand_landmarks, multiplier=self.calib_multiplier
            )
            self.calib_msg = f"Calibrated: T={t:.3f} F={f:.3f}"
        else:
            self.calib_msg = "No hands for calibration"

        def _clear_msg(p: str) -> None:
            time.sleep(3)
            if getattr(self, "calib_msg", "") == p:
                self.calib_msg = ""

        threading.Thread(target=_clear_msg, args=(self.calib_msg,), daemon=True).start()

    def _handle_mode_switch(self) -> None:
        idx = self.modes.index(self.mode)
        old = self.mode
        self.mode = self.modes[(idx + 1) % len(self.modes)]
        self.last_gestures = ["UNKNOWN", "UNKNOWN"]
        self.last_combo = "NONE"
        
        # Prevent hung notes on mode switch
        self._clear_all_hand_midi_notes(0)
        self._clear_all_hand_midi_notes(1)
        self._clear_all_combo_midi_notes()

        self.audio.stop_all_notes()
        logger.info("Mode switch: %s -> %s", old, self.mode)

    def cleanup(self) -> None:
        self.cap.release()
        cv2.destroyAllWindows()
        self.audio.close()
        try:
            if self.midi is not None:
                self.midi.close()
        except Exception:
            pass
        logger.info("Application shut down successfully.")


def main() -> None:
    cfg = load_config()
    setup_logging(cfg)
    logger.info("Starting Air Instrument application")
    app = AirInstrument(cfg)
    app.run()
