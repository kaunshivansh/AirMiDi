import os
import math
import random
import struct
import numpy as np
from scipy.io import wavfile

def create_sound_folder():
    folder = "sounds"
    if not os.path.exists(folder):
        os.makedirs(folder)
    return folder

# --- DRUM SYNTHESIS ---
def _apply_fade(data: np.ndarray, sr: int, fade_ms: float = 2.0) -> np.ndarray:
    fade_len = max(1, int(sr * (fade_ms / 1000.0)))
    if fade_len * 2 > len(data):
        return data
    win = np.hanning(fade_len * 2)
    data[:fade_len] *= win[:fade_len]
    data[-fade_len:] *= win[fade_len:]
    return data


def _normalise_and_write(filename: str, data: np.ndarray, sr: int, target_peak: float = 0.708):
    if data.dtype != np.float32 and data.dtype != np.float64:
        data = data.astype(np.float32)
    # peak-normalise to target_peak (linear)
    peak = np.max(np.abs(data))
    if peak > 0:
        data = data * (target_peak / peak)
    # apply small tanh soft clip to avoid harsh clipping
    out = np.int16(np.clip(data, -1.0, 1.0) * 32767)
    wavfile.write(filename, sr, out)


def generate_kick(filename, sr=44100):
    duration = 0.4
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    freq = 150.0 * np.exp(-40.0 * t) + 45.0
    sample = np.sin(2.0 * math.pi * freq * t) * np.exp(-12.0 * t)
    sample = _apply_fade(sample, sr)
    _normalise_and_write(filename, sample, sr)

def generate_snare(filename, sr=44100):
    duration = 0.3
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    body = np.sin(2.0 * math.pi * 180 * t) * np.exp(-20.0 * t)
    noise = np.random.uniform(-1.0, 1.0, size=t.shape) * np.exp(-15.0 * t)
    sample = body * 0.4 + noise * 0.6
    sample = _apply_fade(sample, sr)
    _normalise_and_write(filename, sample, sr)

def generate_hihat_closed(filename, sr=44100):
    duration = 0.1
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    sample = np.random.uniform(-1.0, 1.0, size=t.shape) * np.exp(-45.0 * t)
    sample = _apply_fade(sample, sr)
    _normalise_and_write(filename, sample, sr)

def generate_hihat_open(filename, sr=44100):
    duration = 0.4
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    sample = np.random.uniform(-1.0, 1.0, size=t.shape) * np.exp(-8.0 * t)
    sample = _apply_fade(sample, sr)
    _normalise_and_write(filename, sample, sr)

def generate_tom(filename, base_freq, sr=44100):
    duration = 0.5
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    freq = base_freq * np.exp(-10.0 * t) + (base_freq * 0.8)
    sample = np.sin(2.0 * math.pi * freq * t) * np.exp(-5.0 * t)
    sample = _apply_fade(sample, sr)
    _normalise_and_write(filename, sample, sr)

def generate_crash(filename, sr=44100):
    duration = 1.5
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    noise = np.random.uniform(-1.0, 1.0, size=t.shape) * np.exp(-3.0 * t)
    metal = np.sin(2.0 * math.pi * 800 * t) * np.exp(-4.0 * t)
    sample = noise * 0.8 + metal * 0.2
    sample = _apply_fade(sample, sr)
    _normalise_and_write(filename, sample, sr)

def generate_ride(filename, sr=44100):
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    ping = np.sin(2.0 * math.pi * 1200 * t) * np.exp(-6.0 * t)
    wash = np.random.uniform(-1.0, 1.0, size=t.shape) * np.exp(-4.0 * t)
    sample = ping * 0.7 + wash * 0.3
    sample = _apply_fade(sample, sr)
    _normalise_and_write(filename, sample, sr)

# --- PIANO SYNTHESIS ---
def generate_piano_wav(filename, freq, sr=44100):
    duration = 2.5
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    env = np.exp(-2.5 * t)
    wave_val = 1.0*np.sin(2.0*np.pi*freq*t) + 0.4*np.sin(2.0*np.pi*(freq*2)*t) + 0.15*np.sin(2.0*np.pi*(freq*3)*t)
    sample = wave_val * env
    sample = _apply_fade(sample, sr)
    _normalise_and_write(filename, sample, sr)

if __name__ == "__main__":
    print("=== SYNTHESIZING FULL STUDIO ASSETS ===")
    folder = create_sound_folder()
    
    # Generate 9-piece kit
    generate_kick(f"{folder}/kick.wav")
    generate_snare(f"{folder}/snare.wav")
    generate_hihat_closed(f"{folder}/hihat.wav")
    generate_hihat_open(f"{folder}/OPENHAT.wav")
    generate_tom(f"{folder}/TOM_HI.wav", 200)
    generate_tom(f"{folder}/TOM_MID.wav", 130)
    generate_tom(f"{folder}/TOM_LOW.wav", 80)
    generate_crash(f"{folder}/CRASH.wav")
    generate_ride(f"{folder}/RIDE.wav")
    
    # Generate Piano
    notes = {"C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23, "G4": 392.00, "A4": 440.00, "B4": 493.88}
    for note, freq in notes.items(): generate_piano_wav(f"{folder}/{note}.wav", freq)
    
    # Verification: list files and sizes
    expected = [
        "kick.wav","snare.wav","hihat.wav","OPENHAT.wav",
        "TOM_HI.wav","TOM_MID.wav","TOM_LOW.wav","CRASH.wav","RIDE.wav",
        "C4.wav","D4.wav","E4.wav","F4.wav","G4.wav","A4.wav","B4.wav"
    ]
    print("[✓] Audio generation complete. Files:")
    for fn in expected:
        p = os.path.join(folder, fn)
        if os.path.exists(p):
            print(f" - {fn}: {os.path.getsize(p)} bytes")
        else:
            print(f" - {fn}: MISSING")