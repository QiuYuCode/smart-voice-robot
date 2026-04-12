# AGENTS.md

This file provides guidelines for agents working in this codebase.

## Project Overview

A voice-controlled robot assistant built with py_trees behavior trees. Supports wake word detection,
ASR (local/cloud), intent recognition, LLM dialogue, camera actions, and TTS.

## Commands

### Setup & Dependencies

```bash
uv sync                    # Install all dependencies
uv sync --extra online     # Install with optional deps (openai, anthropic)
uv add <package>           # Add new dependency
```

### Running

```bash
uv run main.py             # Run the robot assistant
```

### Testing

```bash
uv run test/test_cli.py                         # Interactive mode (keyword matching)
uv run test/test_cli.py "帮我拍照"              # Single command mode
uv run test/test_cli.py --planner               # LLM multi-instruction mode
uv run test/test_cli.py --planner --tts          # Planner mode + TTS
uv run test/test_cli.py --provider deepseek     # Specify LLM provider
```

## Code Style

### Python Version
- Python >= 3.10 required
- Use `from __future__ import annotations` for forward references

### Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Classes | PascalCase | `WaitForWakeWord`, `RobotConfig`, `TakePhotoAction` |
| Functions/methods | snake_case | `execute_take_photo()`, `speak_blocking()` |
| Variables | snake_case | `dialog_audio_queue`, `user_command` |
| Constants | SCREAMING_SNAKE | `SAMPLE_RATE`, `CHUNK_SIZE`, `MSG_TYPE_HANDSHAKE` |
| Private functions | _leading_underscore | `_create_llm()`, `_split_tts_segments()` |
| Dataclass fields | snake_case | `wake_mode`, `llm_provider`, `tts_speaker_id` |
| Module names | snake_case | `nodes/`, `listen.py`, `llm_dialog.py` |

### Import Organization (PEP 8)

```python
# Standard library imports
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Third-party imports
import numpy as np
import py_trees
from py_trees.behaviour import Behaviour
from py_trees.common import Status

# Local application imports
from config import RobotConfig, SAMPLE_RATE
from engine import VoiceEngine
from nodes import WaitForWakeWord, SpeakResponse
```

### Optional Dependencies Pattern

```python
try:
    import cv2
except ImportError:
    cv2 = None
```

### Type Hints

- Use type hints for function parameters and return values
- Use union types with `|` (Python 3.10+): `float | None`
- Typed collections: `list[str]`, `dict[str, list[str]]`

```python
def execute_record_video(config: RobotConfig, duration: float | None = None) -> str:
def _split_tts_segments(self, text: str) -> list[tuple[str, str]]:
```

### Docstrings

Use Google-style docstrings in Chinese or English:

```python
def execute_take_photo(config: RobotConfig) -> str:
    """拍照核心逻辑。成功返回结果描述，失败抛出 RuntimeError。
    
    Args:
        config: Robot configuration object.
        
    Returns:
        Result description string.
        
    Raises:
        RuntimeError: If camera is unavailable.
    """
```

### Error Handling

**Pattern 1: Graceful degradation with fallback**
```python
try:
    return self._generate_iflytek_tts(text)
except Exception as e:
    print(f"[TTS][Cloud] 失败: {e}")
    if not self.config.cloud_tts_fallback_to_local:
        raise
    return self._generate_local_tts(segments)
```

**Pattern 2: RuntimeError for expected failures**
```python
if cv2 is None:
    raise RuntimeError("相机依赖缺失，请先安装 opencv-python。")
```

**Pattern 3: Silent fail with fallback**
```python
try:
    self.blackboard.is_speaking = False
except Exception:
    pass
```

**Pattern 4: Logging errors**
```python
except RuntimeError as e:
    self.logger.error(str(e))
    self.blackboard.response_text = str(e)
    return Status.FAILURE
```

### Logging

Use module-level logger pattern:

```python
logger = logging.getLogger(__name__)

# In methods
self.logger.info("执行: 拍照")
self.logger.error("相机打开失败: %s", str(e))
```

### Blackboard Pattern (py_trees)

All inter-node communication uses py_trees Blackboard with `namespace="dialog"`:

```python
self.blackboard = self.attach_blackboard_client(
    name="TakePhotoAction", namespace="dialog"
)
self.blackboard.register_key(key="intent", access=py_trees.common.Access.READ)
self.blackboard.register_key(key="response_text", access=py_trees.common.Access.WRITE)
```

### Behaviour Node Structure

```python
class MyAction(Behaviour):
    """Docstring describing the node's purpose."""
    
    def __init__(self, name: str, config: RobotConfig):
        super().__init__(name)
        self._config = config
        # Register blackboard keys in __init__
    
    def initialise(self):
        """Called once when behaviour first ticks."""
        pass
    
    def update(self) -> Status:
        """Called every tick. Return SUCCESS, FAILURE, or RUNNING."""
        if condition:
            return Status.FAILURE
        # ... do work ...
        return Status.SUCCESS
    
    def terminate(self, new_status):
        """Called when behaviour stops."""
        pass
```

## Architecture Notes

- **Two intent modes**: Keyword matching (default) or LLM planner mode
- **Config over code**: All parameters in `config.py` dataclass
- **Graceful degradation**: Fallback to local TTS/ASR if cloud fails
- **UI messages in Chinese**: User-facing messages use Chinese
- **Selector pattern**: Actions return FAILURE if intent doesn't match

## Key Files

- `main.py` - Entry point and tree creation
- `config.py` - All configurable parameters
- `engine.py` - VoiceEngine (KWS/ASR/VAD/TTS management)
- `nodes/` - Behavior tree nodes (wake_word, listen, intent, speak, actions/*)
- `test/test_cli.py` - CLI testing tool for single command testing
