import os
import shutil
import sys
from pathlib import Path

import numpy as np
import torch

from modules.sed.ontology import ALL_SOURCES


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_REPO_PATH = Path(__file__).resolve().parents[2] / "third_party" / "PretrainedSED"
_DEFAULT_CHECKPOINT_DIR = Path(__file__).resolve().parents[2] / "resources"
_VALID_ENCODERS = ("M2D", "BEATs", "ATST-F")

_INSTANCE_CACHE: dict[tuple[str, str], "SEDModel"] = {}


class SEDModel:
    """Loads and wraps a PretrainedSED encoder behind PredictionsWrapper.

    Caches one instance per (encoder, device) pair process-wide so the model is
    loaded at most once.
    """

    def __init__(
        self,
        encoder: str = "M2D",
        device: str = "cpu",
        repo_path: Path | str | None = None,
        checkpoint_dir: Path | str | None = None,
    ):
        if encoder not in _VALID_ENCODERS:
            raise ValueError(
                f"encoder must be one of {_VALID_ENCODERS}, got {encoder!r}"
            )

        self.encoder = encoder
        self.device = device
        self.repo_path = Path(repo_path) if repo_path else _DEFAULT_REPO_PATH
        self.checkpoint_dir = (
            Path(checkpoint_dir) if checkpoint_dir else _DEFAULT_CHECKPOINT_DIR
        )

        self._ensure_repo_on_path()
        self._stage_checkpoint()
        self._wrapper = self._build_wrapper()

        from data_util.audioset_classes import as_strong_train_classes  # type: ignore
        self.frame_classes: list[str] = list(as_strong_train_classes)

        missing = sorted(set(ALL_SOURCES) - set(self.frame_classes))
        if missing:
            raise RuntimeError(
                "Ontology source labels not found in framework's class list "
                f"({len(missing)} missing): {missing[:5]}..."
            )

        index_lookup = {name: i for i, name in enumerate(self.frame_classes)}
        self.source_indices: np.ndarray = np.array(
            [index_lookup[name] for name in ALL_SOURCES], dtype=np.int64
        )

    def _ensure_repo_on_path(self) -> None:
        if not self.repo_path.exists():
            raise FileNotFoundError(
                f"PretrainedSED framework not found at {self.repo_path}. "
                f"Run scripts/setup_pretrainedsed.sh to clone it."
            )
        repo_str = str(self.repo_path)
        if repo_str not in sys.path:
            sys.path.insert(0, repo_str)

    def _stage_checkpoint(self) -> None:
        """Ensure `<encoder>_strong_1.pt` is available in a local `resources/`
        folder relative to CWD (PredictionsWrapper resolves checkpoint names
        relative to this folder). Downloads from the upstream GitHub release if
        no copy is cached in `self.checkpoint_dir`."""
        ckpt_name = f"{self.encoder}_strong_1.pt"
        source = self.checkpoint_dir / ckpt_name

        if not source.exists():
            self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
            url = (
                "https://github.com/fschmid56/PretrainedSED/releases/"
                f"download/v0.0.1/{ckpt_name}"
            )
            print(f"Downloading {ckpt_name} from {url}...")
            from torch.hub import download_url_to_file

            download_url_to_file(url, str(source))

        local_dir = Path.cwd() / "resources"
        local_dir.mkdir(exist_ok=True)
        local_path = local_dir / ckpt_name
        if not local_path.exists():
            shutil.copy(source, local_path)

    def _build_wrapper(self) -> torch.nn.Module:
        from models.prediction_wrapper import PredictionsWrapper  # type: ignore

        if self.encoder == "M2D":
            from models.m2d.M2D_wrapper import M2DWrapper  # type: ignore

            wrapper = M2DWrapper()
            model = PredictionsWrapper(
                wrapper,
                checkpoint=f"{self.encoder}_strong_1",
                embed_dim=wrapper.m2d.cfg.feature_d,
            )
        elif self.encoder == "BEATs":
            from models.beats.BEATs_wrapper import BEATsWrapper  # type: ignore

            wrapper = BEATsWrapper()
            model = PredictionsWrapper(
                wrapper, checkpoint=f"{self.encoder}_strong_1"
            )
        else:  # ATST-F
            from models.atstframe.ATSTF_wrapper import ATSTWrapper  # type: ignore

            wrapper = ATSTWrapper()
            model = PredictionsWrapper(
                wrapper, checkpoint=f"{self.encoder}_strong_1"
            )

        model.eval().to(self.device)
        return model

    @torch.no_grad()
    def forward(self, chunk_t: torch.Tensor) -> torch.Tensor:
        """Run encoder front-end + strong head on a (1, n_samples) tensor.

        Returns: tensor of shape (n_classes, n_frames) containing per-frame
        sigmoid probabilities. Multi-label.
        """
        if chunk_t.device != torch.device(self.device):
            chunk_t = chunk_t.to(self.device)
        mel = self._wrapper.mel_forward(chunk_t)
        y_strong, _ = self._wrapper(mel)
        return torch.sigmoid(y_strong).squeeze(0)


def get_sed_model(
    encoder: str = "M2D",
    device: str = "cpu",
    repo_path: Path | str | None = None,
    checkpoint_dir: Path | str | None = None,
) -> SEDModel:
    """Process-wide singleton accessor. Returns the same SEDModel instance for
    repeated calls with matching (encoder, device)."""
    key = (encoder, device)
    if key not in _INSTANCE_CACHE:
        _INSTANCE_CACHE[key] = SEDModel(
            encoder=encoder,
            device=device,
            repo_path=repo_path,
            checkpoint_dir=checkpoint_dir,
        )
    return _INSTANCE_CACHE[key]
