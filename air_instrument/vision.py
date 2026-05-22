from __future__ import annotations

import logging
import os
import sys
from typing import Any

import cv2
import mediapipe as mp
import numpy as np

logger = logging.getLogger(__name__)


class HandTracker:
    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self.cfg = cfg or {}
        model_path = "hand_landmarker.task"
        if not os.path.exists(model_path):
            logger.info("Downloading MediaPipe hand landmark model...")
            import urllib.request

            url = (
                "https://storage.googleapis.com/mediapipe-models/"
                "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
            )
            try:
                urllib.request.urlretrieve(url, model_path)
            except Exception as e:
                logger.error("Failed to download MediaPipe model: %s", e)
                sys.exit(1)

        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=2,
            min_hand_detection_confidence=0.7,
            min_hand_presence_confidence=0.7,
            min_tracking_confidence=0.7,
        )
        self.detector = vision.HandLandmarker.create_from_options(options)

        gcfg = (self.cfg.get("gesture") if isinstance(self.cfg, dict) else {}) or {}
        try:
            self.thumb_dot_threshold = float(gcfg.get("thumb_thresh", -0.05))
        except Exception:
            self.thumb_dot_threshold = -0.05
        try:
            self.finger_cos_threshold = float(gcfg.get("finger_thresh", -0.25))
        except Exception:
            self.finger_cos_threshold = -0.25

    def get_landmarks(self, frame: np.ndarray) -> Any:
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
        return self.detector.detect(mp_image)

    def _to_vec(self, landmarks: Any, i: int) -> np.ndarray:
        pt = landmarks[i]
        return np.array([pt.x, pt.y, getattr(pt, "z", 0.0)], dtype=np.float32)

    def calibrate_from_landmarks(
        self,
        hand_landmarks_list: list[Any],
        multiplier: float = 0.5,
    ) -> tuple[float, float]:
        thumb_dots: list[float] = []
        finger_coss: list[float] = []

        for hl in hand_landmarks_list:
            try:
                palm_vec = self._to_vec(hl, 17) - self._to_vec(hl, 5)
                norm = np.linalg.norm(palm_vec) + 1e-9
                palm_vec = palm_vec / norm

                v_thumb = self._to_vec(hl, 4) - self._to_vec(hl, 3)
                v_thumb = v_thumb / (np.linalg.norm(v_thumb) + 1e-9)
                thumb_dots.append(float(np.dot(v_thumb, palm_vec)))

                for tip_id, pip_id in [(8, 6), (12, 10), (16, 14), (20, 18)]:
                    v_tip = self._to_vec(hl, tip_id) - self._to_vec(hl, pip_id)
                    v_mcp = self._to_vec(hl, 5) - self._to_vec(hl, pip_id)
                    denom = np.linalg.norm(v_tip) * np.linalg.norm(v_mcp) + 1e-9
                    cos = float(np.dot(v_tip, v_mcp) / denom)
                    finger_coss.append(cos)
            except Exception:
                continue

        if thumb_dots:
            td_mean = float(np.mean(thumb_dots))
            td_std = float(np.std(thumb_dots))
            new_thumb = td_mean - multiplier * td_std
        else:
            new_thumb = self.thumb_dot_threshold

        if finger_coss:
            fc_mean = float(np.mean(finger_coss))
            fc_std = float(np.std(finger_coss))
            new_finger = fc_mean - multiplier * fc_std
        else:
            new_finger = self.finger_cos_threshold

        self.thumb_dot_threshold = float(new_thumb)
        self.finger_cos_threshold = float(new_finger)
        return self.thumb_dot_threshold, self.finger_cos_threshold

    def count_fingers(self, hand_landmarks: Any) -> tuple[int, list[bool]]:
        def lm(i: int) -> np.ndarray:
            return self._to_vec(hand_landmarks, i)

        mcp_index = lm(5)
        finger_tips = [4, 8, 12, 16, 20]
        finger_pips = [3, 6, 10, 14, 18]

        states: list[bool] = []

        try:
            palm_vec = lm(17) - lm(5)
            palm_vec = palm_vec / (np.linalg.norm(palm_vec) + 1e-9)
        except Exception:
            palm_vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        v_thumb = lm(4) - lm(3)
        v_thumb = v_thumb / (np.linalg.norm(v_thumb) + 1e-9)
        thumb_extended = float(np.dot(v_thumb, palm_vec)) > self.thumb_dot_threshold
        states.append(thumb_extended)

        for tip_id, pip_id in zip(finger_tips[1:], finger_pips[1:]):
            v_tip = lm(tip_id) - lm(pip_id)
            v_mcp = mcp_index - lm(pip_id)
            denom = np.linalg.norm(v_tip) * np.linalg.norm(v_mcp) + 1e-9
            cos = float(np.dot(v_tip, v_mcp) / denom)
            states.append(cos < self.finger_cos_threshold)

        count = int(sum(states))
        return count, states

    def detect_gesture(
        self,
        hand_landmarks: Any,
        finger_states: list[bool] | tuple[bool, ...] | np.ndarray,
    ) -> str:
        states = [bool(x) for x in finger_states]
        fingers_count = int(sum(states))
        thumb_up, index_up, middle_up, ring_up, pinky_up = states

        if fingers_count == 0:
            return "FIST"
        if fingers_count == 5:
            return "OPEN"
        if fingers_count == 4:
            return "FOUR"
        if fingers_count == 1 and index_up:
            return "POINTER"
        if fingers_count == 2 and index_up and middle_up:
            return "PEACE"
        if fingers_count == 2 and thumb_up and pinky_up:
            return "SHAKA"
        if fingers_count == 3 and index_up and middle_up and ring_up:
            return "THREE"
        if fingers_count == 2 and index_up and pinky_up:
            return "ROCK"

        return f"{fingers_count}_FINGERS"
