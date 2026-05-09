"""Smoke test for SEDDetector against the real PretrainedSED model.

Skipped automatically if the framework or checkpoint is not available — this
keeps the suite green on machines that don't have the model weights yet.
"""

from pathlib import Path
from typing import get_args

import numpy as np
import pytest

from contracts.types import SEDInput, SoundClass


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_PATH = _BACKEND_ROOT / "third_party" / "PretrainedSED"
_CHECKPOINT = _BACKEND_ROOT / "resources" / "M2D_strong_1.pt"

_skip_reason = None
if not _REPO_PATH.exists():
    _skip_reason = f"PretrainedSED repo not cloned at {_REPO_PATH}"
elif not _CHECKPOINT.exists():
    _skip_reason = f"M2D checkpoint missing at {_CHECKPOINT}"

pytestmark = pytest.mark.skipif(
    _skip_reason is not None, reason=_skip_reason or ""
)


@pytest.fixture(scope="module")
def detector():
    from modules.sed.inference import SEDDetector

    return SEDDetector(encoder="M2D", device="cpu")


def test_silent_chunk(detector, silent_chunk_1s):
    out = detector.detect(
        SEDInput(
            audio_chunk=silent_chunk_1s,
            sample_rate=16000,
            timestamp=0.0,
            window_id=0,
        )
    )
    assert out.window_id == 0
    assert out.sound_class in get_args(SoundClass)
    assert 0.0 <= out.confidence <= 1.0
    # Silent input should not trigger a detection.
    assert out.detected is False


def test_noise_chunk(detector, noise_chunk_1s):
    out = detector.detect(
        SEDInput(
            audio_chunk=noise_chunk_1s,
            sample_rate=16000,
            timestamp=1.0,
            window_id=1,
        )
    )
    assert out.window_id == 1
    assert out.sound_class in get_args(SoundClass)
    assert 0.0 <= out.confidence <= 1.0


def test_wrong_sample_rate_rejected(detector):
    with pytest.raises(ValueError):
        detector.detect(
            SEDInput(
                audio_chunk=np.zeros(8000, dtype=np.float32),
                sample_rate=8000,
                timestamp=0.0,
                window_id=0,
            )
        )
