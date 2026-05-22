# 📻 Air Instrument & DAW Controller

A premium, gesture-controlled MIDI controller and sample-based software instrument featuring a modern real-time visual HUD.

By tracking your hand gestures and 3D spatial coordinates in real time using a standard webcam, this application triggers MIDI notes and modulates continuous control (CC) parameters dynamically. It connects seamlessly to professional Digital Audio Workstations (DAWs) like **Ableton Live**, **Logic Pro**, **FL Studio**, **Reaper**, or **GarageBand** as an external MIDI hardware device.

---

## 🚀 Features

*   **⚡ Real-Time Gesture Tracking**: High-precision hand landmark tracking powered by Google MediaPipe.
*   **🎹 Three Expressive Modes**:
    *   `PIANO`: 7-note melodic mode optimized for lead synth/piano solos.
    *   `DRUMS`: 9-part drum kit mapping for finger drumming/beat-making.
    *   `COMBO`: Unified mapping of 8 single-hand sounds and 8 advanced two-hand chord/percussion combinations.
*   **🎛️ 3D Continuous Expression (MIDI CC)**:
    *   **Y-Axis (Height)** ➡️ Default: `CC 1` (Modulation Wheel). Higher hand positions open up the mod-wheel.
    *   **X-Axis (Width)** ➡️ Default: `CC 10` (Stereo Pan). Left/right movements pan the sound.
    *   **Z-Axis (Depth/Palm Size)** ➡️ Default: `CC 74` (Brightness / Filter Cutoff). Bringing your hand closer to the camera opens the synthesizer filter.
*   **🥁 Speed-Sensitive Dynamic Velocity**: Tracks hand movement speed across frames to calculate note trigger velocity dynamically (`40` to `127`).
*   **🔒 Zero Stuck/Hung Notes**:
    *   *Active Note Tracking*: Clears playing MIDI notes automatically when hand gestures change or when hands leave the camera frame.
    *   *Percussive Auto-Off*: Automatically fires MIDI `note_off` events after exactly `100ms` for drum sounds to prevent sustained pads or frozen percussion hits in your DAW.
    *   *Safe Shutdown*: Sends a MIDI `All Notes Off` (CC 123) sweep on all active channels upon application termination.
*   **💻 Native Virtual MIDI Port**:
    *   Creates a native virtual MIDI device named **`AirInstrument`** on macOS.
    *   Gracefully falls back to physical or virtual ports (such as loopMIDI) on Windows and Linux.
*   **🔊 Built-in Sampler Engine**: High-fidelity local sample playback engine with editable stereo feedback delay/echo FX, enabling operation without any DAW.
*   **⏺️ Session Recorder**: Record and save jams locally to `recordings/` as standard 16-bit stereo `.wav` audio files.
*   **🎯 Live Calibration**: Calibrate hand tracking thresholds instantly (`[c]` key) using your camera feed.

---

## 🛠️ Installation & Setup

### 1. Prerequisites
*   Python **3.10 to 3.12** is recommended.
*   A functional webcam.
*   On macOS, MIDI virtual ports are supported natively. On Windows, you will need a virtual MIDI driver like **[loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html)** to bridge the application to your DAW.

### 2. Install Dependencies
Clone the repository, initialize a virtual environment, and install requirements:

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Generate High-Fidelity Audio Assets
Run the built-in studio sound synthesizer to generate the 16 drum and piano samples used by the local audio engine:

```bash
python setup_sounds.py
```

### 4. Run the Application
Start the instrument:

```bash
python air_instrument.py
```

---

## 🎮 Controls & Interface

### Keyboard Commands
| Key | Action | Description |
| :---: | :--- | :--- |
| **`M`** | Switch Mode | Cycle through `PIANO` ➡️ `DRUMS` ➡️ `COMBO` modes. |
| **`C`** | Calibrate | Hold your open hand flat in front of the camera for 3 seconds to auto-tune detection thresholds. |
| **`R`** | Record | Toggle performance recording on/off (saves to `recordings/` folder). |
| **`P`** | Pause/Resume | Pause/resume the current recording session. |
| **`Space`** | Playback | Play back the last recorded WAV session through the local audio engine. |
| **`Q`** | Quit | Safely close MIDI ports, release the camera, and exit. |

---

## 📖 Gesture Mapping Guide

### Melodic Notes (Melodic Channel - default 0/Channel 1)
Melodic instruments are mapped to standard Western scale pitches:
*   `C4` = 60 | `D4` = 62 | `E4` = 64 | `F4` = 65 | `G4` = 67 | `A4` = 69 | `B4` = 71

### Drum Mappings (Percussive Channel - default 9/Channel 10)
Drums follow General MIDI standards:
*   `Kick` = 36 | `Snare` = 38 | `Hi-hat (Closed)` = 42 | `Open Hat` = 46 | `Tom Low` = 45 | `Tom Mid` = 48 | `Tom High` = 50 | `Crash` = 49 | `Ride` = 51

---

### Single-Hand Gestures
These gestures are active across different modes:

| Hand Gesture | Extended Fingers | `PIANO` Mode | `DRUMS` Mode | `COMBO` Mode |
| :--- | :---: | :---: | :---: | :---: |
| **FIST** | None | *(Silent)* | Kick | Kick |
| **POINTER** | Index | C4 | Snare | D4 |
| **PEACE** | Index, Middle | D4 | Hi-hat (Closed) | Snare |
| **THREE** | Index, Middle, Ring | E4 | Tom High | E4 |
| **FOUR** | Index, Middle, Ring, Pinky | F4 | Tom Mid | F4 |
| **OPEN** | All Fingers | G4 | Open Hat | Hi-hat (Closed) |
| **ROCK** | Index, Pinky | A4 | Crash | Crash |
| **SHAKA** | Thumb, Pinky | B4 | Ride | Ride |

---

### Two-Hand Combinations (`COMBO` Mode Only)
When two hands are visible in `COMBO` mode, finger counts are combined (order-independent) to trigger complex hits:

| Combined Finger Counts | Gesture Combo | Mapped Sound / Note | MIDI Note Number |
| :---: | :--- | :---: | :---: |
| **`0 + 1`** | FIST + POINTER | **C4** | 60 |
| **`1 + 2`** | POINTER + PEACE | **G4** | 67 |
| **`2 + 3`** | PEACE + THREE | **A4** | 69 |
| **`3 + 4`** | THREE + FOUR | **B4** | 71 |
| **`0 + 5`** | FIST + OPEN | **Tom Low** | 45 |
| **`1 + 5`** | POINTER + OPEN | **Tom Mid** | 48 |
| **`2 + 5`** | PEACE + OPEN | **Tom High** | 50 |
| **`0 + 2`** | FIST + PEACE | **Open Hat** | 46 |

---

## 🎛️ 3D Coordinate Modulation Mapping

Continuous control (CC) expressions are calculated from the coordinates of your primary hand (Hand 0):

```
       [Top of Screen]
       CC 1 (Modulation) = 127
             ^
             |
[Left] <----------- [Right]
CC 10 (Pan) = 0     CC 10 (Pan) = 127
             |
             v
       CC 1 (Modulation) = 0
      [Bottom of Screen]

  (Depth / Z-Axis: Distance between wrist and knuckle)
  [Hand Far / Small]  -----------------> [Hand Near / Large]
  CC 74 (Filter Cutoff) = 0             CC 74 (Filter Cutoff) = 127
```

> [!TIP]
> **Duplicate CC Suppression**: The controller tracks the last value sent for each CC. It only broadcasts a MIDI message if the value changes, saving valuable bandwidth and preventing CPU spikes in your DAW.

---

## 🔌 DAW Integration Guide

Connecting the Air Instrument to a DAW takes only a minute. Ensure the app is running **before** launching your DAW so the virtual port is registered.

### 🎛️ General DAW Configuration
1. Start `air_instrument.py`.
2. Open your DAW's **MIDI Preferences**.
3. Under MIDI Inputs, locate **`AirInstrument`** (or your loopMIDI fallback port).
4. Enable **Track** (to receive notes/velocity) and **Remote** (to receive CC mappings).

---

### 🟩 Ableton Live Setup
1. Open **Preferences** ➡️ **Link/Tempo/MIDI**.
2. Locate `Input: AirInstrument` under the MIDI Ports list.
3. Check the boxes for **Track** and **Remote**.
4. Create a MIDI track and set **MIDI From** to `AirInstrument`.
5. Arm the track and load your favorite VST synth (e.g., Serum, Vital, Wavetable).
6. To assign the spatial axes to synth knobs:
   * Click the **MIDI** map button at the top-right of Live (or press `Cmd + M` / `Ctrl + M`).
   * Click the parameter you want to modulate (e.g., Synth Filter Cutoff).
   * Move your hand closer/further (Z-axis) or left/right (X-axis) until the mapping registers.
   * Press `Cmd + M` / `Ctrl + M` to exit mapping mode.

---

### 🎚️ Logic Pro Setup
1. Open Logic Pro ➡️ **Settings** ➡️ **MIDI** ➡️ **Inputs**.
2. Ensure `AirInstrument` is ticked.
3. Add a Software Instrument track and set the input channel to **All** or **Channel 1**.
4. Load an instrument like *Retro Synth* or *Alchemy*.
5. Control CC values directly:
   * The Y-axis (Modulation Wheel) will automatically control default modulation parameters.
   * To assign X or Z coordinates to specific parameters, use **Smart Controls** (`L` key) or the **Controller Assignments** panel (`Shift + Option + K`).
   * Move your hand in the target axis to complete the assignment.

---

### 🍍 FL Studio Setup
1. Open **MIDI Settings** (`F10`).
2. Select **`AirInstrument`** in the Input list.
3. Set **Enable** to active. Choose a unique **Controller Type** (e.g., Generic Controller).
4. Load a plugin into the Channel Rack (e.g., 3xOsc, Harmor, Sytrus).
5. To map coordinates to knobs:
   * Right-click any knob inside FL Studio and select **Link to controller...**.
   * Move your hand along the desired axis (X, Y, or Z/Depth) in front of the camera.
   * FL Studio will auto-detect the CC message and bind the control.

---

## ⚙️ Configuration Reference (`config.yaml`)

You can customize thresholds, camera parameters, and MIDI CC destinations in the `config.yaml` file located in the root directory:

```yaml
audio:
  sample_rate: 44100
  blocksize: 256          # Lower blocksizes reduce latency but increase CPU load
  delay_feedback: 0.35    # Echo decay volume multiplier
  delay_ms: 400           # Built-in echo duration

gesture:
  confirm_frames: 3       # Number of consecutive matching frames to trigger a gesture
  thumb_thresh: -0.05     # Thumb threshold (overridden by calibration)
  finger_thresh: -0.25    # Finger fold threshold (overridden by calibration)
  calib_duration_s: 3     # Calibration hold duration
  min_hand_confidence: 0.7 # Minimum landmark detection confidence (0.0 - 1.0)

camera:
  device_index: 0         # Change this index (e.g. 1 or 2) if using an external webcam
  width: 1280
  height: 720

midi:
  enabled: true
  port_name: "virtual"    # Use "virtual" on macOS, or specify physical port name/index
  channel: 0              # Melodic Channel (0 = Channel 1)
  drum_channel: 9         # Percussive Channel (9 = Channel 10)
  velocity:
    mode: "dynamic"       # "dynamic" (velocity based on hand speed) or "fixed"
    default_value: 100    # Default velocity if in fixed mode
  expression:
    enabled: true
    y_axis:
      cc_number: 1        # Modulation Wheel
      min_value: 0
      max_value: 127
      invert: true        # Inverted so moving hand UP increases CC value
    x_axis:
      cc_number: 10       # Pan
      min_value: 0
      max_value: 127
      invert: false
    z_axis:
      cc_number: 74       # Filter Cutoff/Brightness
      min_value: 0
      max_value: 127
      invert: false
```

---

## 🛠️ Troubleshooting

#### 1. Stuck / Hung Notes in DAW
*   Ensure that you are not moving your hand out of the camera's sight before resetting your gesture.
*   If your hand leaves the frame, the application automatically clears all active notes. Check that your webcam has good lighting so that MediaPipe does not drop hand tracking frames unexpectedly.

#### 2. Virtual Port Not Showing on Windows
*   Virtual MIDI ports are unsupported by the Windows OS driver stack natively. You must install **loopMIDI** and add a port named `"loopMIDI Port"` (or any custom name).
*   In `config.yaml`, change the `port_name` from `"virtual"` to the exact name of the port you created in loopMIDI (e.g. `"loopMIDI Port"`), or set it to `0` to open the first available port.

#### 3. High Audio Latency (Local Sampler Engine)
*   If you are running the built-in local sampler engine and notice delay between making a gesture and hearing the sound, decrease the `blocksize` under `audio` in `config.yaml` to `128` or `64` (if your CPU/audio driver supports low block sizes).
*   For professional production, use a DAW configured with **ASIO drivers** (Windows) or **CoreAudio** (macOS).

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
