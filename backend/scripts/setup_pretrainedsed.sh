#!/usr/bin/env bash
# Clone the PretrainedSED framework and install its requirements.
# Run from project root after activating the venv.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THIRD_PARTY_DIR="${PROJECT_ROOT}/third_party"
REPO_DIR="${THIRD_PARTY_DIR}/PretrainedSED"
REPO_URL="https://github.com/fschmid56/PretrainedSED.git"

mkdir -p "${THIRD_PARTY_DIR}"

if [ -d "${REPO_DIR}/.git" ]; then
    echo "PretrainedSED already cloned at ${REPO_DIR} — skipping clone."
else
    echo "Cloning PretrainedSED into ${REPO_DIR}..."
    git clone --depth 1 "${REPO_URL}" "${REPO_DIR}"
fi

echo "Installing PretrainedSED requirements..."
pip install -r "${REPO_DIR}/requirements.txt"

mkdir -p "${PROJECT_ROOT}/resources"

echo ""
echo "Setup complete."
echo "Next: place the M2D checkpoint at ${PROJECT_ROOT}/resources/M2D_strong_1.pt"
echo "(See ${REPO_URL} for download instructions.)"
