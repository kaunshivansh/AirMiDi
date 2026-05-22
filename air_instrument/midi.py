from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DRUM_SOUNDS: set[str] = {
    "kick",
    "snare",
    "hihat",
    "OPENHAT",
    "TOM_HI",
    "TOM_MID",
    "TOM_LOW",
    "CRASH",
    "RIDE",
}


class MidiOut:
    SOUND_TO_NOTE: dict[str, int] = {
        "C4": 60,
        "D4": 62,
        "E4": 64,
        "F4": 65,
        "G4": 67,
        "A4": 69,
        "B4": 71,
        "kick": 36,
        "snare": 38,
        "hihat": 42,
        "OPENHAT": 46,
        "TOM_HI": 50,
        "TOM_MID": 48,
        "TOM_LOW": 45,
        "CRASH": 49,
        "RIDE": 51,
    }

    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self.cfg = cfg or {}
        self.enabled = bool(self.cfg.get("enabled", True))
        self.port_name = self.cfg.get("port_name", "virtual")
        self.channel = int(self.cfg.get("channel", 0))
        self.drum_channel = int(self.cfg.get("drum_channel", 9))
        self.active_port_name = "None"
        
        # State to track last CC values to prevent flooding DAW with duplicate MIDI messages
        self._last_cc_values: dict[int, int] = {}
        self._midi = None

        if not self.enabled:
            return

        try:
            import rtmidi

            self._midi = rtmidi.MidiOut()
            ports = self._midi.get_ports()

            if self.port_name == "virtual":
                try:
                    self._midi.open_virtual_port("AirInstrument")
                    self.active_port_name = "Virtual: AirInstrument"
                    logger.info("MIDI virtual port 'AirInstrument' opened")
                except (NotImplementedError, Exception) as e:
                    logger.warning(
                        "Virtual MIDI port not supported or failed (%s). Falling back to physical port.", e
                    )
                    if ports:
                        self._midi.open_port(0)
                        self.active_port_name = ports[0]
                        logger.info("Opened fallback MIDI port: %s", ports[0])
                    else:
                        logger.warning("No MIDI output ports available.")
                        self.enabled = False
            else:
                port_idx = -1
                if isinstance(self.port_name, int):
                    if 0 <= self.port_name < len(ports):
                        port_idx = self.port_name
                elif isinstance(self.port_name, str):
                    for idx, name in enumerate(ports):
                        if self.port_name.lower() in name.lower():
                            port_idx = idx
                            break

                if port_idx != -1:
                    self._midi.open_port(port_idx)
                    self.active_port_name = ports[port_idx]
                    logger.info("Opened MIDI port: %s", ports[port_idx])
                elif ports:
                    self._midi.open_port(0)
                    self.active_port_name = ports[0]
                    logger.info("Opened default MIDI port: %s", ports[0])
                else:
                    logger.warning("No MIDI output ports available.")
                    self.enabled = False
        except Exception as e:
            logger.warning("MIDI initialization failed: %s", e)
            self.enabled = False

    def list_ports(self) -> list[str]:
        if self._midi:
            try:
                return self._midi.get_ports()
            except Exception:
                pass
        return []

    def note_on(self, sound_name: str, velocity: int = 100) -> None:
        if not self.enabled or self._midi is None or sound_name not in self.SOUND_TO_NOTE:
            return
        note = self.SOUND_TO_NOTE[sound_name]
        ch = self.drum_channel if sound_name in DRUM_SOUNDS else self.channel
        velocity = max(0, min(127, velocity))
        try:
            self._midi.send_message([0x90 | (ch & 0x0F), note, velocity])
        except Exception as e:
            logger.error("MIDI note_on error: %s", e)

    def note_off(self, sound_name: str) -> None:
        if not self.enabled or self._midi is None or sound_name not in self.SOUND_TO_NOTE:
            return
        note = self.SOUND_TO_NOTE[sound_name]
        ch = self.drum_channel if sound_name in DRUM_SOUNDS else self.channel
        try:
            self._midi.send_message([0x80 | (ch & 0x0F), note, 0])
        except Exception as e:
            logger.error("MIDI note_off error: %s", e)

    def control_change(self, cc_number: int, value: int, channel: int | None = None) -> None:
        if not self.enabled or self._midi is None:
            return
        
        ch = self.channel if channel is None else channel
        cc_number = max(0, min(127, cc_number))
        value = max(0, min(127, value))
        
        # Suppress duplicates to avoid MIDI flood
        if self._last_cc_values.get(cc_number) == value:
            return
            
        self._last_cc_values[cc_number] = value
        try:
            self._midi.send_message([0xB0 | (ch & 0x0F), cc_number, value])
        except Exception as e:
            logger.error("MIDI CC error: %s", e)

    def pitch_bend(self, value: int, channel: int | None = None) -> None:
        """Sends a pitch bend message. Value range is 0 to 16383 (centered at 8192)."""
        if not self.enabled or self._midi is None:
            return
            
        ch = self.channel if channel is None else channel
        value = max(0, min(16383, value))
        lsb = value & 0x7F
        msb = (value >> 7) & 0x7F
        
        try:
            self._midi.send_message([0xE0 | (ch & 0x0F), lsb, msb])
        except Exception as e:
            logger.error("MIDI pitch_bend error: %s", e)

    def close(self) -> None:
        if self.enabled and self._midi is not None:
            try:
                # Send MIDI All Notes Off command to avoid hung notes on close
                for ch in {self.channel, self.drum_channel}:
                    self._midi.send_message([0xB0 | (ch & 0x0F), 123, 0])
                self._midi.close_port()
            except Exception:
                pass
            self.enabled = False
