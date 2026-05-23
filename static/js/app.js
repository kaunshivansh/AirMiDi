const videoElement = document.getElementsByClassName('input_video')[0];
const canvasElement = document.getElementsByClassName('output_canvas')[0];
const canvasCtx = canvasElement.getContext('2d');
const midiOutSelect = document.getElementById('midi-out');
const statusDiv = document.getElementById('status');
const activeNoteDiv = document.getElementById('active-note');

let midiAccess = null;
let selectedOutput = null;
let lastGesture = "UNKNOWN";
let activeNote = null;

// Standard MIDI notes for C Major scale starting at C4
const noteMapping = {
    "POINTER": 60, // C4
    "PEACE": 62,   // D4
    "THREE": 64,   // E4
    "FOUR": 65,    // F4
    "OPEN": 67,    // G4
    "ROCK": 69,    // A4
    "SHAKA": 71,   // B4
    "FIST": 36     // Kick
};

// --- Web MIDI Setup ---
if (navigator.requestMIDIAccess) {
    navigator.requestMIDIAccess().then(onMIDISuccess, onMIDIFailure);
} else {
    midiOutSelect.innerHTML = '<option value="">Web MIDI not supported</option>';
    statusDiv.innerText = "Web MIDI API not supported in this browser.";
}

function onMIDISuccess(midi) {
    midiAccess = midi;
    updateMidiOutputs();
    midi.onstatechange = updateMidiOutputs;
    
    midiOutSelect.addEventListener('change', (e) => {
        const id = e.target.value;
        if (id && midiAccess) {
            selectedOutput = midiAccess.outputs.get(id);
            console.log("MIDI Output Selected:", selectedOutput.name);
        } else {
            selectedOutput = null;
        }
    });
}

function updateMidiOutputs() {
    const prevSelection = midiOutSelect.value;
    midiOutSelect.innerHTML = '<option value="">Select MIDI Output to DAW...</option>';
    let hasOutputs = false;
    for (let output of midiAccess.outputs.values()) {
        const option = document.createElement('option');
        option.value = output.id;
        option.text = output.name;
        midiOutSelect.appendChild(option);
        hasOutputs = true;
    }
    
    if (!hasOutputs) {
        midiOutSelect.innerHTML = '<option value="">No MIDI outputs found. Create a virtual loopback port.</option>';
    } else if (prevSelection) {
        midiOutSelect.value = prevSelection;
    }
}

function onMIDIFailure() {
    midiOutSelect.innerHTML = '<option value="">MIDI Access Denied</option>';
    statusDiv.innerText = "Could not access MIDI devices.";
}

function sendNoteOn(note) {
    if (selectedOutput) {
        // Channel 1 (0x90), Note, Velocity 100
        selectedOutput.send([0x90, note, 100]); 
    }
    activeNote = note;
    activeNoteDiv.innerText = `Note: ${note}`;
}

function sendNoteOff(note) {
    if (selectedOutput && note !== null) {
        // Channel 1 (0x80), Note, Velocity 0
        selectedOutput.send([0x80, note, 0]); 
    }
    activeNote = null;
    activeNoteDiv.innerText = `Note: None`;
}

// --- Gesture Logic ---
function countFingers(landmarks) {
    const tips = [4, 8, 12, 16, 20];
    const pips = [3, 6, 10, 14, 18];
    const mcp = [2, 5, 9, 13, 17];
    let states = [];
    
    // Thumb: robust check based on distance to pinky base vs index base
    // If thumb tip is further out sideways
    let thumbIsOut = false;
    // Assuming hands are mostly upright, check if thumb tip x is outside thumb mcp x
    // Account for left/right hand mirroring implicitly by looking at absolute distances
    const thumbDistToPinky = Math.abs(landmarks[tips[0]].x - landmarks[mcp[4]].x);
    const thumbMcpDistToPinky = Math.abs(landmarks[mcp[0]].x - landmarks[mcp[4]].x);
    thumbIsOut = thumbDistToPinky > thumbMcpDistToPinky * 1.2; 
    states.push(thumbIsOut);

    // Other 4 fingers: tip is above pip (y is smaller)
    for (let i = 1; i < 5; i++) {
        states.push(landmarks[tips[i]].y < landmarks[pips[i]].y);
    }
    
    return states;
}

function detectGesture(states) {
    const [t, i, m, r, p] = states;
    if (i && !m && !r && !p) return "POINTER";
    if (i && m && !r && !p) return "PEACE";
    if (i && m && r && !p) return "THREE";
    if (!t && i && m && r && p) return "FOUR";
    if (t && i && m && r && p) return "OPEN";
    if (!t && i && !m && !r && p) return "ROCK"; // Changed from strict 'i && p' to not include thumb
    if (t && !i && !m && !r && p) return "SHAKA";
    if (!t && !i && !m && !r && !p) return "FIST";
    return "UNKNOWN";
}

// Gesture buffering to avoid flickering
let gestureBuffer = [];
const BUFFER_SIZE = 3;

// --- MediaPipe Hand Tracking ---
function onResults(results) {
    canvasCtx.save();
    canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);
    
    // Draw mirrored video frame
    if (results.image) {
        canvasCtx.scale(-1, 1);
        canvasCtx.translate(-canvasElement.width, 0);
        canvasCtx.drawImage(results.image, 0, 0, canvasElement.width, canvasElement.height);
        canvasCtx.translate(canvasElement.width, 0);
        canvasCtx.scale(-1, 1);
    }

    if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
        statusDiv.innerText = "Tracking Hand...";
        statusDiv.className = "active";
        
        const landmarks = results.multiHandLandmarks[0];
        const mirroredLandmarks = landmarks.map(lm => ({...lm, x: 1 - lm.x}));
        
        drawConnectors(canvasCtx, mirroredLandmarks, HAND_CONNECTIONS, {color: '#555', lineWidth: 2});
        drawLandmarks(canvasCtx, mirroredLandmarks, {color: '#00ffff', lineWidth: 1, radius: 3});

        const states = countFingers(mirroredLandmarks); // Use mirrored for gesture logic? It's symmetric mostly
        // Wait, thumb logic relies on x. For mirrored, it works if we use distances.
        const unmirroredStates = countFingers(landmarks);
        
        const rawGest = detectGesture(unmirroredStates);
        
        // Stabilize gesture
        gestureBuffer.push(rawGest);
        if (gestureBuffer.length > BUFFER_SIZE) gestureBuffer.shift();
        
        const allSame = gestureBuffer.every(g => g === gestureBuffer[0]);
        let gest = lastGesture;
        
        if (gestureBuffer.length === BUFFER_SIZE && allSame) {
            gest = gestureBuffer[0];
        }

        // Draw gesture name at hand center
        canvasCtx.font = "24px 'Segoe UI'";
        canvasCtx.fillStyle = "#00ffff";
        const cx = mirroredLandmarks[9].x * canvasElement.width;
        const cy = mirroredLandmarks[9].y * canvasElement.height;
        canvasCtx.fillText(gest, cx + 20, cy - 20);
        
        // Draw target reticle
        canvasCtx.beginPath();
        canvasCtx.arc(cx, cy, 10, 0, 2 * Math.PI);
        canvasCtx.strokeStyle = "#00ffff";
        canvasCtx.stroke();

        // MIDI Trigger logic
        if (gest !== lastGesture) {
            if (activeNote !== null) {
                sendNoteOff(activeNote);
            }
            if (noteMapping[gest]) {
                sendNoteOn(noteMapping[gest]);
            }
            lastGesture = gest;
        }
    } else {
        statusDiv.innerText = "No hand detected.";
        statusDiv.className = "";
        if (lastGesture !== "UNKNOWN") {
            if (activeNote !== null) {
                sendNoteOff(activeNote);
            }
            lastGesture = "UNKNOWN";
        }
        gestureBuffer = [];
    }
    canvasCtx.restore();
}

const hands = new Hands({locateFile: (file) => {
  return `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`;
}});
hands.setOptions({
  maxNumHands: 1,
  modelComplexity: 1,
  minDetectionConfidence: 0.6,
  minTrackingConfidence: 0.6
});
hands.onResults(onResults);

const camera = new Camera(videoElement, {
  onFrame: async () => {
    await hands.send({image: videoElement});
  },
  width: 640,
  height: 480
});

// Start camera
statusDiv.innerText = "Initializing camera...";
camera.start().catch(err => {
    console.error("Camera error:", err);
    statusDiv.innerText = "Camera access denied or failed.";
});