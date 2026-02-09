# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **py_trees behavior tree learning project** focused on building a voice-controlled assistant system. The main implementation (`voice_assistant.py`) demonstrates a complete voice interaction loop: idle → wake word detection → command listening → intent recognition → action execution → response → idle.

**Key Technologies:**
- **py_trees 2.4+**: Behavior tree framework for state management
- **Vosk 0.3+**: Offline speech recognition (Chinese models)
- **pyttsx3 2.91+**: Text-to-speech engine
- **OpenCV 4.13+**: Camera control
- **SpeechRecognition**: Audio input handling

## Development Commands

### Environment Setup
```bash
# Install dependencies using uv (preferred)
uv sync

# Or using pip
pip install -r requirements.txt  # if available
# Or install from pyproject.toml
pip install -e .
```

### Running the Application
```bash
# Main voice assistant
python voice_assistant.py

# Test guide (interactive)
python test_voice_assistant.py

# Visualize behavior tree
python visualize_tree.py

# Configuration validation
python config.py
```

### Vosk Model Setup
The system requires a Vosk Chinese speech recognition model:
```bash
# Download small model (~40MB)
wget https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip
unzip vosk-model-small-cn-0.22.zip -d model/

# Update config.py with model path
VOSK_MODEL_PATH = "/path/to/model/small"
```

## Architecture

### Behavior Tree Structure

The voice assistant uses a hierarchical behavior tree with the following key patterns:

**Root Selector (memory=True)**: Manages state transitions between idle and active modes
- **WakeWordDetector**: Idle state - continuously listens for wake words
- **ActiveState**: Active state - handles dialog flow with interrupt capability
  - **Parallel (SuccessOnOne)**: Enables interrupt functionality
    - **InterruptMonitor**: Parallel thread monitoring for interrupt commands
    - **DialogLoop (Sequence, memory=False)**: Main conversation flow
      - PlayWakeupSound → ListenForCommand → RecognizeIntent → ExecuteAction → PlayResponseSound → CheckDialogTimeout

### Key Design Patterns

1. **Selector + memory=True**: Maintains state between ticks, prevents unnecessary resets
2. **Parallel + SuccessOnOne**: Implements true interrupt capability - when InterruptMonitor succeeds, entire dialog terminates
3. **Sequence + memory=False**: Enables looping conversations - resets after completion for next iteration
4. **Blackboard (namespace="dialog")**: Shared data store for inter-node communication

### Blackboard Variables

All nodes share data through the blackboard with namespace `"dialog"`:
- `state`: Global system state ("idle" | "active")
- `wake_word_detected`: Boolean flag for wake word detection
- `command_text`: User's voice command text
- `intent`: Recognized intent from command
- `interrupt_command`: Interrupt command text
- `last_activity_time`: Timestamp for timeout detection
- `response_text`: TTS response text

## Configuration

All system parameters are centralized in `config.py`:

**Critical paths to update:**
- `VOSK_MODEL_PATH`: Path to Vosk model directory
- `CAMERA_DEVICE_INDEX`: Camera device index (default: 0)

**Customizable parameters:**
- `WAKE_WORDS`: List of wake word phrases
- `INTERRUPT_WORDS`: List of interrupt phrases
- `DIALOG_TIMEOUT`: Seconds before auto-idle (default: 10)
- `TTS_RATE`: Speech rate (80-300, default: 150)
- `INTENT_PATTERNS`: Keyword patterns for intent recognition

## Adding New Commands

To add a new voice command:

1. **Add intent pattern** in `config.py`:
```python
INTENT_PATTERNS = {
    "your_intent": ["keyword1", "keyword2"],
}
```

2. **Create action node** in `voice_assistant.py`:
```python
class YourAction(py_trees.behaviour.Behaviour):
    def __init__(self, name="YourAction"):
        super().__init__(name)
        self.blackboard = py_trees.blackboard.Client(
            name="YourClient", namespace="dialog"
        )
        self.blackboard.register_key(key="intent", access=py_trees.common.Access.READ)
        self.blackboard.register_key(key="response_text", access=py_trees.common.Access.WRITE)

    def update(self):
        if self.blackboard.intent != "your_intent":
            return py_trees.common.Status.FAILURE

        # Your action logic here
        self.blackboard.response_text = "Action completed"
        return py_trees.common.Status.SUCCESS
```

3. **Add to action selector** in `create_tree()`:
```python
action_selector.add_children([
    YourAction(),
    OpenCameraAction(),
    # ... other actions
])
```

## Node Lifecycle

All behavior nodes implement the py_trees lifecycle:
- `setup()`: One-time initialization (load models, connect hardware)
- `initialise()`: Called when node starts executing
- `update()`: Called every tick, returns Status.SUCCESS/FAILURE/RUNNING
- `terminate(status)`: Called when node finishes
- `shutdown()`: Cleanup when tree shuts down

## Thread Safety

The system uses `MIC_LOCK` (threading.Lock) to prevent concurrent microphone access. Always acquire this lock before using the microphone in any node.

## Common Issues

**Microphone not detected:**
```python
import speech_recognition as sr
print(sr.Microphone.list_microphone_names())
```

**TTS not working on Linux:**
```bash
sudo apt-get install espeak
```

**ALSA errors:** Already suppressed in code via ctypes error handler

**Wake word recognition issues:**
- Use larger Vosk model for better accuracy
- Adjust `ENERGY_THRESHOLD` in config.py
- Add more wake word variations

## File Structure

- `voice_assistant.py`: Main implementation (~700 lines, 12 behavior nodes)
- `config.py`: Centralized configuration (~200 lines)
- `main.py`: Original simple example code
- `visualize_tree.py`: Tree visualization utility
- `test_voice_assistant.py`: Interactive test guide
- `model/`: Vosk speech recognition models
- `source/`: C code for UART communication (unrelated to main project)

## Testing

Run the test guide for 6 predefined scenarios:
```bash
python test_voice_assistant.py
```

Scenarios include: wake-idle cycle, camera control, weather/music queries, interrupt functionality, unknown commands, timeout behavior.

## Debugging

Enable detailed logging:
```python
# In voice_assistant.py
log_tree.Level = log_tree.Level.DEBUG
```

Visualize tree structure:
```bash
python visualize_tree.py
# Generates: voice_assistant_tree.{dot,png,svg}
```

Monitor blackboard state by adding to any node's `update()`:
```python
self.logger.debug(f"Blackboard: {dict(self.blackboard)}")
```
