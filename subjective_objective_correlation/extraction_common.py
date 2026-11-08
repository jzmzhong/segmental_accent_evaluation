"""Shared audio-pair discovery and cache loading for independent extraction scripts."""

from pathlib import Path
import re

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
TEMP_DIR = SCRIPT_DIR.parent / "data_temp"
DEFAULT_SPEAKERS = (
    "69e8b0adf78ba4d3ede8b1f5", "6a08fea524e9dc84ff9a258a",
    "66fc6008cda3d277a8978dbf", "69f8709095bf5e9416de1057",
)
FEATURE_MODELS = ("f0_formants", "ppg", "ecapatdnn", "wavlm", "genaid", "voxlect")
FRAME_CACHE_FILENAMES = {name: f"{name}_frame.pt" for name in FEATURE_MODELS}
UTTERANCE_CACHE_FILENAMES = {name: f"{name}_utterance.pt" for name in FEATURE_MODELS}

CANDIDATE_PATTERN = re.compile(
    r"cloned_(?P<speaker>[0-9a-f]+)_(?P<utterance>(?:comma|wolf)_\d{3})_"
    r"ref_(?:comma|wolf)_\d{3}_(?:maskgct|f5tts|sparc)$"
)


def load_cache(path):
    import torch
    return torch.load(path, map_location="cpu", weights_only=True) if path.exists() else {}


def candidate_pairs(wav_dir, target_speakers):
    for candidate in sorted(wav_dir.rglob("cloned_*.wav")):
        match = CANDIDATE_PATTERN.fullmatch(candidate.stem)
        if match is None:
            print(f"Skipping unrecognised filename: {candidate.name}")
            continue
        speaker, utterance = match.group("speaker", "utterance")
        if target_speakers and speaker not in target_speakers:
            continue
        reference = candidate.with_name(f"{speaker}_{utterance}.wav")
        if not reference.is_file():
            print(f"Skipping {candidate.name}: missing reference {reference}")
            continue
        yield reference, candidate

