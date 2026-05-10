#!/usr/bin/env bash
# Uninstall the training-only Python packages that were dragged in by the
# upstream PretrainedSED/requirements.txt but are NOT used on the inference
# path.  Inference itself only needs what's listed in backend/requirements.txt.
#
# Run from the project root with the project venv active.
# Safe to run repeatedly — pip just reports "not installed" for missing names.

set -euo pipefail

# ── Top-level packages we never import at inference time ───────────────────
# NOT in this list (despite looking trainee-only): torchvision (timm),
# huggingface_hub + safetensors (timm), pydantic (ollama), audioop-lts
# (librosa on Python 3.13+).  Removing those WILL break inference.
TRAINING_ONLY=(
    pytorch-lightning
    lightning-utilities
    torchmetrics
    transformers
    tokenizers
    datasets
    wandb
    sentry-sdk
    gitpython
    gitdb
    smmap
    h5py
    jsonpickle
    hf_transfer
    hf-fastup
    hf-xet
    intervaltree
    sortedcontainers
    pyarrow
    pandas
    multiprocess
    dill
    xxhash
    aiohttp
    aiohappyeyeballs
    aiosignal
    frozenlist
    multidict
    propcache
    yarl
    standard-aifc
    standard-chunk
    standard-sunau
)

echo "Uninstalling training-only packages…"
pip uninstall -y "${TRAINING_ONLY[@]}" 2>/dev/null || true

echo
echo "Done. Verify the inference path still imports cleanly:"
echo "  cd backend && PYTHONPATH=. python -c 'from modules.sed.interface import SEDModel; from modules.doa.interface import DOAModel; print(\"OK\")'"
echo
echo "Then re-install the slim inference set if anything was over-pruned:"
echo "  pip install -r backend/requirements.txt"
