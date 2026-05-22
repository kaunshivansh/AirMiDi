from __future__ import annotations

import copy
import logging
import logging.handlers
import pathlib
from typing import Any

try:
    import yaml
except Exception:
    yaml = None

DEFAULT_CONFIG: dict[str, Any] = {
    "audio": {
        "sample_rate": 44100,
        "blocksize": 256,
        "delay_feedback": 0.35,
        "delay_ms": 400,
        "master_vol": 0.85,
    },
    "gesture": {
        "confirm_frames": 3,
        "thumb_thresh": -0.05,
        "finger_thresh": -0.25,
        "calib_duration_s": 3,
        "calib_multiplier": 0.5,
        "min_hand_confidence": 0.7,
    },
    "camera": {
        "device_index": 0,
        "width": 1280,
        "height": 720,
    },
    "recording": {
        "folder": "recordings",
        "format": "wav",
    },
    "logging": {
        "level": "INFO",
        "file": "logs/air_instrument.log",
        "max_bytes": 10485760,
        "backup_count": 5,
    },
    "midi": {
        "enabled": True,
        "port_name": "virtual",
        "channel": 0,
        "drum_channel": 9,
        "velocity": {
            "mode": "dynamic",
            "default_value": 100,
        },
        "expression": {
            "enabled": True,
            "y_axis": {
                "cc_number": 1,
                "min_value": 0,
                "max_value": 127,
                "invert": True,
            },
            "x_axis": {
                "cc_number": 10,
                "min_value": 0,
                "max_value": 127,
                "invert": False,
            },
            "z_axis": {
                "cc_number": 74,
                "min_value": 0,
                "max_value": 127,
                "invert": False,
            },
        },
    },
}


def _deep_update(a: dict, b: dict) -> None:
    for k, v in (b or {}).items():
        if k in a and isinstance(a[k], dict) and isinstance(v, dict):
            _deep_update(a[k], v)
        else:
            a[k] = v


def load_config(path: str = "config.yaml") -> dict[str, Any]:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if yaml is None:
        logging.getLogger(__name__).warning(
            "PyYAML not installed - using default configuration"
        )
        return cfg
    try:
        with open(path) as fh:
            user: dict | None = yaml.safe_load(fh)
            _deep_update(cfg, user or {})
    except FileNotFoundError:
        pass
    return cfg


def setup_logging(cfg: dict[str, Any]) -> None:
    p = pathlib.Path(cfg["logging"]["file"])
    p.parent.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, cfg["logging"]["level"].upper(), logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(
        cfg["logging"]["file"],
        maxBytes=cfg["logging"]["max_bytes"],
        backupCount=cfg["logging"]["backup_count"],
    )
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = []
    root.addHandler(fh)
    root.addHandler(sh)
