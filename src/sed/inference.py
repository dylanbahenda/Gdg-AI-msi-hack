from pathlib import Path

import numpy as np
import torch

from sed.model import SEDModel, get_sed_model
from sed.ontology import MACRO_DETECTION_THRESHOLDS, MACRO_TO_SOURCES
from sed.types import SEDInput, SEDOutput, SoundClass


_TARGET_SAMPLE_RATE = 16000


class SEDDetector:
    """One-chunk-in, one-detection-out wrapper around the PretrainedSED model.

    Collapses the framework's multi-label, per-frame sigmoid output into a
    single (sound_class, confidence) by:
      1. Zero-padding the input chunk to `window_size_seconds`.
      2. Running the encoder, slicing the output frames back to the real-audio span.
      3. Per macro: max over (its source-class probabilities × real frames).
      4. argmax across macros.
    """

    def __init__(
        self,
        encoder: str = "M2D",
        device: str = "cpu",
        detection_threshold: float = 0.1,
        window_size_seconds: float = 10.0,
        repo_path: Path | str | None = None,
        checkpoint_dir: Path | str | None = None,
    ):
        self.detection_threshold = detection_threshold
        self.window_size_seconds = window_size_seconds
        self._window_samples = int(window_size_seconds * _TARGET_SAMPLE_RATE)

        self._model: SEDModel = get_sed_model(
            encoder=encoder,
            device=device,
            repo_path=repo_path,
            checkpoint_dir=checkpoint_dir,
        )

        # Precompute per-macro index slices into the 447-class probability tensor.
        self._macros: list[SoundClass] = list(MACRO_TO_SOURCES.keys())
        index_lookup = {name: i for i, name in enumerate(self._model.frame_classes)}
        self._macro_indices: dict[SoundClass, np.ndarray] = {
            macro: np.array(
                [index_lookup[name] for name in sources], dtype=np.int64
            )
            for macro, sources in MACRO_TO_SOURCES.items()
        }

    def detect(self, input: SEDInput) -> SEDOutput:
        if input.sample_rate != _TARGET_SAMPLE_RATE:
            raise ValueError(
                f"sample_rate must be {_TARGET_SAMPLE_RATE}, got {input.sample_rate}"
            )

        chunk = input.audio_chunk.astype(np.float32, copy=False)
        n_real = chunk.shape[0]

        if n_real >= self._window_samples:
            padded = chunk[: self._window_samples]
            real_samples = self._window_samples
        else:
            padded = np.zeros(self._window_samples, dtype=np.float32)
            padded[:n_real] = chunk
            real_samples = n_real

        chunk_t = torch.from_numpy(padded).unsqueeze(0)
        probs = self._model.forward(chunk_t).cpu().numpy()  # (n_classes, n_frames)
        n_frames = probs.shape[1]

        real_frames = max(
            1, round(n_frames * (real_samples / self._window_samples))
        )
        probs_real = probs[:, :real_frames]

        best_macro: SoundClass = self._macros[0]
        best_score: float = -1.0
        for macro in self._macros:
            indices = self._macro_indices[macro]
            score = float(probs_real[indices].max())
            if score > best_score:
                best_score = score
                best_macro = macro

        threshold = MACRO_DETECTION_THRESHOLDS.get(best_macro, self.detection_threshold)
        return SEDOutput(
            window_id=input.window_id,
            timestamp=input.timestamp,
            sound_class=best_macro,
            confidence=best_score,
            detected=best_score >= threshold,
        )
