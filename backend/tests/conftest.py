import numpy as np
import pytest


@pytest.fixture
def silent_chunk_1s() -> np.ndarray:
    return np.zeros(16000, dtype=np.float32)


@pytest.fixture
def noise_chunk_1s() -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.standard_normal(16000).astype(np.float32) * 0.1
