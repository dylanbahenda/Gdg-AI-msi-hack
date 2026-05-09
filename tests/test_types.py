from dataclasses import fields, is_dataclass
from typing import get_args

import numpy as np

from sed.types import SEDInput, SEDOutput, SoundClass


EXPECTED_CLASSES = (
    "clap",
    "crying",
    "broken_glass",
    "doorbell",
    "metal_sound",
    "alarm",
    "dog",
    "scream",
    "knock",
    "phone",
)


def test_sound_class_literal_matches_contract():
    assert get_args(SoundClass) == EXPECTED_CLASSES


def test_sed_input_fields():
    assert is_dataclass(SEDInput)
    field_names = tuple(f.name for f in fields(SEDInput))
    assert field_names == ("audio_chunk", "sample_rate", "timestamp", "window_id")


def test_sed_output_fields():
    assert is_dataclass(SEDOutput)
    field_names = tuple(f.name for f in fields(SEDOutput))
    assert field_names == (
        "window_id",
        "timestamp",
        "sound_class",
        "confidence",
        "detected",
    )


def test_sed_input_construction():
    chunk = np.zeros(16000, dtype=np.float32)
    inp = SEDInput(audio_chunk=chunk, sample_rate=16000, timestamp=1.0, window_id=0)
    assert inp.audio_chunk.shape == (16000,)
    assert inp.sample_rate == 16000


def test_sed_output_construction():
    out = SEDOutput(
        window_id=0,
        timestamp=1.0,
        sound_class="doorbell",
        confidence=0.8,
        detected=True,
    )
    assert out.sound_class == "doorbell"
    assert out.detected is True
