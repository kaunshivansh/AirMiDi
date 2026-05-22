# CHANGELOG

All notable changes for Air Instrument.

## Unreleased

- BUG-1: Fixed sound-name case mismatches. `setup_sounds.py` now generates `kick.wav`, `snare.wav`, `hihat.wav` (keeps `OPENHAT.wav`). Added a runtime assertion in `AudioEngine` to fail-fast with a helpful message if required samples are missing.
- BUG-2: Fixed audio callback thread-safety by adding a `threading.Lock` around `active_samples` and snapshotting the list during callback processing.
- BUG-3: Fixed debug-panel overflow by increasing the HUD debug box height to avoid clipped lines.
- BUG-4: Fixed stale gestures when hands disappear by resetting `last_gestures` for missing hand indices.
- BUG-5: Removed fallback code path in `detect_gesture`; `count_fingers` now guarantees a states list and `detect_gesture` asserts the contract.

- REL-1: Added gesture confirmation buffers (debounce) using `collections.deque` to require multiple frames before a gesture change triggers sound.
- REL-2: Reduced audio latency by attempting `blocksize=256` and auto-falling-back to `512` / `1024` if necessary.
- REL-3: Vectorised recorder echo processing to avoid slow per-sample Python loops; saves are now fast and CPU-friendly.
- REL-4: Added camera-open check and a clear runtime error if the configured camera index is not available.
- REL-5: Removed unused top-level imports and cleaned model-download handling.

- Feature: Added optional MIDI output (`MidiOut`) using `python-rtmidi`. MIDI notes are emitted alongside audio when enabled in `config.yaml`.
- Config: Added `config.yaml` / `config.example.yaml` and `setup_logging` helper; application reads configuration from `config.yaml`.
- Setup: `setup_sounds.py` hardened — all outputs are Hann-faded (2 ms) and peak-normalised to -3 dBFS; verification print added.
- Infrastructure: Added `requirements.txt` with pinned versions.
