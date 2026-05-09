# SELD — SED Module

Sound Event Detection module for the SELD pipeline. Wraps the [PretrainedSED](https://github.com/fschmid56/PretrainedSED) framework (M2D encoder by default) and exposes the dataclass contract from [docs/infernceclass.md](docs/infernceclass.md).

## Setup

```bash
source .venv/bin/activate
pip install -e ".[dev]"

bash scripts/setup_pretrainedsed.sh
# Then place M2D_strong_1.pt at: resources/M2D_strong_1.pt
```

## Usage

```python
from sed import SEDDetector, SEDInput

detector = SEDDetector(encoder="M2D", device="cpu")  # loads once
out = detector.detect(SEDInput(
    audio_chunk=chunk,        # np.float32 in [-1, 1], 16 kHz mono
    sample_rate=16000,
    timestamp=ts,
    window_id=k,
))
# out.sound_class, out.confidence, out.detected
```

## Tests

```bash
pytest                     # all tests; real-model tests auto-skip if checkpoint absent
pytest -v -k 'not real'    # only fast tests
```

## Latency benchmark

```bash
python scripts/benchmark_latency.py --encoder M2D --device cpu --n 100
```

## Class ontology

10 user-facing macros — see [docs/infernceclass.md](docs/infernceclass.md) and [src/sed/ontology.py](src/sed/ontology.py).
