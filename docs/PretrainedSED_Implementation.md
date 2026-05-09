# PretrainedSED — Implementation in the Waterfall Pipeline

This document describes how **PretrainedSED** is integrated and used as the
refinement stage of the cascading Sound Event Detection pipeline implemented
in [codici_sed/SED_waterfall/SED_model.ipynb](codici_sed/SED_waterfall/SED_model.ipynb).
It covers only the PretrainedSED side of the system (model loading,
configuration, inference, post-processing, ontology mapping). The Level-1
screening stage is intentionally excluded.

---

## 1. What "PretrainedSED" Is in This Project

PretrainedSED is **not a single model** — it is the open-source framework
hosted at `https://github.com/fschmid56/PretrainedSED`, which exposes three
interchangeable AudioSet-strong-label foundation encoders behind a common
`PredictionsWrapper`:

- **M2D** — Masked Modeling Duo (default in this project)
- **BEATs** — Audio Pre-Training with Acoustic Tokenizers
- **ATST-F** — Audio Spectrogram Transformer (Frame-level)

All three are pre-trained on **AudioSet** and produce **frame-level
probabilities over 456 strong-label classes** at a **16 kHz** input sample
rate. The user-facing ontology of the project picks ~57 of these 456 classes
and maps them to ~30 final categories.

In the cascade, PretrainedSED is the **second (refinement) stage**: it
receives a 16 kHz waveform plus a list of time regions of interest and
returns precise frame-level detections within those regions.

---

## 2. Repository Setup and Dependencies

The framework is cloned at runtime by `EnvironmentSetup` (cell 12 of
`SED_model.ipynb`):

```python
git clone --depth 1 https://github.com/fschmid56/PretrainedSED.git <repo_path>
pip install -r <repo_path>/requirements.txt
```

Where `<repo_path>` is environment-dependent:

| Environment | Path |
|---|---|
| Colab | `/content/PretrainedSED` |
| Local | `./PretrainedSED` |

The repo path is appended to `sys.path` so that its modules become
importable:

```python
sys.path.append(self.config.pretrained_sed_repo_path)
```

---

## 3. Checkpoints

Each encoder uses its own strong-label checkpoint, named with the pattern
`{MODEL}_strong_1.pt`:

| File | Encoder |
|---|---|
| `M2D_strong_1.pt` | M2D |
| `BEATs_strong_1.pt` | BEATs |
| `ATST-F_strong_1.pt` | ATST-F |

Default storage locations:

| Environment | Base path |
|---|---|
| Colab | `/content/drive/MyDrive/SED_checkpoints/PretrainedSED/resources/` |
| Local | `./checkpoints/PretrainedSED/resources/` |

Before instantiating the model, `ModelManager._load_sed_model` **copies the
checkpoint into a local `resources/` folder in the current working
directory** because `PredictionsWrapper` resolves checkpoint names relative
to a `resources/` folder:

```python
local_resources_folder = 'resources'
os.makedirs(local_resources_folder, exist_ok=True)
local_checkpoint_path = os.path.join(local_resources_folder,
                                     f"{sed_model_name}_strong_1.pt")
if not os.path.exists(local_checkpoint_path):
    shutil.copy(sed_source_path, local_checkpoint_path)
```

This copy happens once per encoder and is cached for subsequent runs.

---

## 4. Model Loading

The framework's wrappers are imported from the cloned repo:

```python
from models.m2d.M2D_wrapper        import M2DWrapper
from models.beats.BEATs_wrapper    import BEATsWrapper
from models.atstframe.ATSTF_wrapper import ATSTWrapper
from models.prediction_wrapper     import PredictionsWrapper
```

A single `PredictionsWrapper` instance wraps the chosen encoder. The
instantiation differs per encoder because M2D requires the embedding
dimension to be passed explicitly:

```python
if sed_model_name == 'M2D':
    wrapper = M2DWrapper()
    sed_model = PredictionsWrapper(
        wrapper,
        checkpoint="M2D_strong_1",
        embed_dim=wrapper.m2d.cfg.feature_d,
    )
elif sed_model_name == 'BEATs':
    wrapper = BEATsWrapper()
    sed_model = PredictionsWrapper(wrapper, checkpoint="BEATs_strong_1")
elif sed_model_name == 'ATST-F':
    wrapper = ATSTWrapper()
    sed_model = PredictionsWrapper(wrapper, checkpoint="ATST-F_strong_1")

sed_model.eval().to(device)
```

`ModelManager.change_sed_model(new_name)` allows swapping the encoder at
runtime without restarting the pipeline; it nulls the previous instance and
re-runs `_load_sed_model`.

---

## 5. Configuration Surface

The relevant fields of `SEDConfig` (cell 10) for PretrainedSED:

| Field | Default | Meaning |
|---|---|---|
| `sed_model_name` | `'M2D'` | Encoder choice: `M2D`, `BEATs`, or `ATST-F` |
| `sed_padding_seconds` | `5.0` | Context padding added before/after every input region |
| `sed_window_size_seconds` | `10.0` | Sliding-window length at 16 kHz |
| `sed_hop_size_seconds` | `5.0` | Hop between consecutive windows (50% overlap) |
| `sed_merge_tolerance_seconds` | `0.5` | Max gap to merge same-label detections |
| `device` | `'cuda'` if available else `'cpu'` | Inference device |
| `sed_checkpoint_base_path` | env-dependent (see §3) | Where checkpoints live before being copied locally |
| `pretrained_sed_repo_path` | env-dependent (see §2) | Cloned framework location |

`update_model(name)` validates against `{'M2D', 'BEATs', 'ATST-F'}` and
raises on anything else.

---

## 6. Audio Preparation

`AudioProcessor.load_audio` decodes the input file with FFmpeg twice (once
per required sample rate). For PretrainedSED, the relevant call is:

```python
ffmpeg -i <file> -f s16le -ac 1 -ar 16000 -
```

The 16 kHz, mono, 16-bit PCM stream is read from FFmpeg's stdout and
normalized to `float32` in `[-1, 1]`:

```python
waveform_int16   = np.frombuffer(raw_audio, dtype=np.int16)
waveform_float32 = waveform_int16.astype(np.float32) / 32768.0
```

The resulting `waveform_16k` array is what feeds the PretrainedSED stage.

---

## 7. Inference (`PretrainedSEDAnalyzer.analyze_segments`)

The analyzer receives `waveform_16k` and a list of `(start_sec, end_sec)`
regions. Logic, in order:

### 7.1 Region padding

Each input region is widened by `sed_padding_seconds = 5.0 s` on both sides,
clamped to the audio bounds:

```python
padded_start = max(0, start_sec - 5.0)
padded_end   = min(audio_duration_sec, end_sec + 5.0)
segment      = waveform_16k[int(padded_start*16000) : int(padded_end*16000)]
```

The 5 s pre/post pad supplies temporal context to the encoder, which is
beneficial for transformer-based models with non-trivial receptive fields.

### 7.2 Sliding window

Within each padded segment, the analyzer slides a fixed window:

- `window_samples = 10 s × 16 000 = 160 000`
- `hop_samples    = 5 s × 16 000  = 80 000` (50 % overlap)

The last (potentially short) chunk is **right-zero-padded** to a full window
to keep tensor shapes constant:

```python
if len(chunk) < window_samples:
    chunk = np.pad(chunk, (0, window_samples - len(chunk)))
```

A flag `is_padded_chunk` is kept so that fake detections inside the padded
tail can be filtered later.

### 7.3 Forward pass

Every chunk is moved to the device and run through the model in `no_grad`
mode:

```python
chunk_tensor = torch.from_numpy(chunk[None, :]).to(device)
with torch.no_grad():
    mel        = sed_model.mel_forward(chunk_tensor)   # waveform → mel
    y_strong, _ = sed_model(mel)                        # frame-level logits
probs = torch.sigmoid(y_strong).squeeze(0).cpu().numpy()  # (n_classes, n_frames)
```

Notes:
- Mel-spectrogram computation is delegated to the model's
  `mel_forward` (each encoder ships its own front-end with the correct
  parameters).
- Only the **strong (frame-level) head** `y_strong` is used. The second
  return value (clip-level prediction) is discarded with `_`.
- The output is sigmoid-activated — strong-label classes are
  **multi-label**, not softmaxed.

### 7.4 Per-class thresholding

Class names are read from the framework's
`data_util.audioset_classes.as_strong_train_classes` (456 entries). Only
classes that exist in the project ontology are processed. Each class has its
own threshold supplied by `SEDOntology.get_threshold(label)` (default
`0.1`, range `0.02–0.3` — see §9). Frames are binarized by direct
comparison:

```python
active_frames = (class_probs > threshold).astype(int)
```

### 7.5 Onset/offset extraction

Edges of contiguous `active_frames` runs are recovered via difference of a
zero-padded mask:

```python
padded_actives = np.concatenate(([0], active_frames, [0]))
diffs          = np.diff(padded_actives)
onset_frames   = np.where(diffs ==  1)[0]
offset_frames  = np.where(diffs == -1)[0]
```

Frame indices are converted to seconds using the **encoder-agnostic** rate

```python
frames_per_sec = len(class_probs) / sed_window_size_seconds  # = T / 10
```

so the same code works for M2D, BEATs and ATST-F regardless of their native
temporal stride.

### 7.6 Padded-chunk guard

If the chunk was zero-padded (last window short), any event whose `onset_sec`
falls **at or after** the real audio length within the chunk is discarded:

```python
if onset_sec >= real_audio_len_sec:
    if is_padded_chunk:
        # debug log + drop event
        continue
```

This avoids ghost detections triggered by the silent zero tail.

### 7.7 Global timestamping

Local times are translated to global file time:

```python
chunk_start_sec_global = padded_start + (chunk_start_sample / 16000)
global_onset           = chunk_start_sec_global + onset_sec
global_offset          = chunk_start_sec_global + offset_sec
```

Each detection is appended to a list as a dict
`{event_label, global_onset, global_offset}`. The final return value is a
`pandas.DataFrame` (empty if no detections).

---

## 8. Post-Processing (`ResultProcessor`)

### 8.1 Per-label merging

Detections are grouped by AudioSet `event_label`, sorted by `global_onset`,
and merged whenever the gap between consecutive events is below
`sed_merge_tolerance_seconds = 0.5 s`:

```python
if row['global_onset'] - last_event['global_offset'] < tolerance:
    last_event['global_offset'] = max(last_event['global_offset'],
                                      row['global_offset'])
else:
    merged.append(row.to_dict())
```

Note: merging is **per AudioSet label**, not per ontology class. Two
distinct AudioSet labels that map to the same final class (e.g. `Bark` and
`Howl` → `Cane`) remain separate rows.

### 8.2 Ontology mapping and final schema

Each `event_label` is mapped to the user-facing class via
`SEDOntology.get_class_mapping()` (multilingual; see §9). Columns are
renamed for the final output:

```
Classe | Label Dettaglio | Inizio (s) | Fine (s)
```

---

## 9. Ontology

Defined in `SEDOntology` (cell 16). Two dictionaries drive the behaviour:

- `label_to_class_map: AudioSet label → {it: ..., en: ...}` — multilingual
  mapping. Default language is `'en'`. If a translation is missing, English
  is used as fallback; if the label itself is missing, the raw label is
  returned.
- `label_to_threshold_map: AudioSet label → float` — per-class detection
  threshold used in §7.4. Default for unlisted labels is `0.1`.

Examples (selected):

| AudioSet label | EN class | IT class | Threshold |
|---|---|---|---|
| `Gunshot, gunfire` | Firearm | Arma da fuoco | 0.05 |
| `Explosion` | Explosion | Esplosione | 0.10 |
| `Fireworks` | Fireworks | Fuochi d'artificio | 0.30 |
| `Glass shatter` | Glass | Vetro | 0.10 |
| `Clang` | Metal | Metallo | 0.03 |
| `Screaming` | Scream | Urla | 0.02 |
| `Shout` | Scream | Urla | 0.02 |
| `Bark` | Dog | Cane | 0.10 |
| `Door` | Door | Porta | 0.05 |
| `Sliding door` | Garage door | Garage | 0.03 |
| `Thump, thud` | Generic impact | Colpo generico | 0.20 |
| `Vehicle horn, car horn, honking, toot` | Horn | Clacson | 0.10 |
| `Ambulance (siren)` | Siren | Sirena | 0.10 |

Sensitivities are tuned per class: very low (0.02–0.05) for safety-critical
events that must not be missed (screams, gunshots, doors, metallic clinks),
higher (0.20–0.30) for classes prone to false positives in noisy contexts
(fireworks, thumps, slams).

A minor harmless duplication exists in `label_to_threshold_map`:
`"Motor vehicle (road)"` appears twice with the same value `0.1`.

`get_classes_to_use()` returns the list of AudioSet labels that the
ontology cares about — this is the filter applied in §7.4 to skip the
remaining ~400 of the 456 classes.

---

## 10. End-to-End PretrainedSED Flow

Given a 16 kHz waveform `waveform_16k` and a list of regions
`[(t0, t1), ...]`:

1. For each region, pad by ±5 s and slice the waveform.
2. Slide a 10 s / 5 s-hop window over the slice; zero-pad the tail.
3. Run `mel_forward` then `model(mel)`; take `sigmoid(y_strong)`.
4. For each ontology class, threshold the per-frame probabilities,
   extract onset/offset frames via `np.diff`, and convert to seconds with
   `len(probs)/10`.
5. Discard events that start in the zero-padded tail of a short chunk.
6. Reproject local times to the global file timeline.
7. Merge same-label detections within 0.5 s of each other.
8. Map AudioSet labels to user-facing classes (IT/EN).
9. Return a `DataFrame` with columns `Classe`, `Label Dettaglio`,
   `Inizio (s)`, `Fine (s)`.

---

## 11. Caveats and Implementation Notes

- **Window overlap inside padded regions.** Because the analyzer pads each
  region by 5 s and adjacent regions are not deduplicated, overlapping
  audio chunks may be passed through the encoder more than once. The
  per-label merge step in §8.1 absorbs the resulting duplicate detections,
  but it does not save the wasted compute.
- **Frame rate is encoder-agnostic.** `frames_per_sec` is derived from the
  output tensor length rather than hard-coded — works correctly across M2D,
  BEATs and ATST-F regardless of their native temporal stride.
- **Strong head only.** The clip-level head returned by
  `PredictionsWrapper.__call__` is intentionally discarded. All decisions
  are taken at frame granularity.
- **Multi-label sigmoid.** Strong outputs are sigmoid-activated; multiple
  classes can be active at the same frame.
- **Cross-class merging is not performed.** Two AudioSet labels mapped to
  the same `Classe` (e.g. `Bark` + `Howl` → `Cane`) remain as separate
  rows in the final DataFrame.
- **Padded-chunk guard is one-sided.** Events whose *onset* falls inside
  the zero-padded tail are dropped, but events that start inside the real
  audio and *extend* into the padded tail keep their (artificial) offset.
- **Local checkpoint copy.** The `resources/` folder is created in the
  current working directory of the notebook. If the working directory
  changes between sessions, the copy step runs again.
- **Default encoder is M2D.** Project notes report M2D as the most
  balanced choice, BEATs as the most accurate, and ATST-F as the strongest
  for fine temporal localization.
