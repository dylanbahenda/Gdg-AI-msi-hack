from typing import get_args

from modules.sed.ontology import (
    ALL_SOURCES,
    MACRO_TO_SOURCES,
    SOURCE_THRESHOLDS,
    SOURCE_TO_MACRO,
)
from contracts.types import SoundClass


def test_macro_count():
    assert len(MACRO_TO_SOURCES) == 10


def test_macros_match_sound_class_literal():
    assert set(MACRO_TO_SOURCES.keys()) == set(get_args(SoundClass))


def test_source_count():
    assert len(ALL_SOURCES) == 47


def test_sources_disjoint():
    assert len(SOURCE_TO_MACRO) == len(ALL_SOURCES)


def test_thresholds_cover_all_sources():
    assert set(SOURCE_THRESHOLDS.keys()) == set(ALL_SOURCES)


def test_threshold_range():
    for src, t in SOURCE_THRESHOLDS.items():
        assert 0.0 < t < 1.0, f"Threshold for {src!r} out of (0, 1): {t}"


def test_reverse_map_consistency():
    for macro, sources in MACRO_TO_SOURCES.items():
        for src in sources:
            assert SOURCE_TO_MACRO[src] == macro


def test_distinct_whimper_labels():
    """`Whimper` (human, in `crying`) and `Whimper (dog)` (in `dog`) must stay separate."""
    assert SOURCE_TO_MACRO["Whimper"] == "crying"
    assert SOURCE_TO_MACRO["Whimper (dog)"] == "dog"
