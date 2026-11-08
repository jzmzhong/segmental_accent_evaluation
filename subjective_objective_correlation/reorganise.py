#!/usr/bin/env python3
"""Prepare speaker folders containing matching WAV and transcript files.

Usage: python reorganise.py RAW_DATA_DIR DATA_TEMP_DIR
"""

import re
import shutil
import sys
from pathlib import Path

raw_dir, temp_dir = map(Path, sys.argv[1:])
speakers = {
    "69e8b0adf78ba4d3ede8b1f5",
    "6a08fea524e9dc84ff9a258a",
    "66fc6008cda3d277a8978dbf",
    "69f8709095bf5e9416de1057",
}
pairs = []
for wav in sorted((raw_dir / "wav").rglob("*.wav")):
    speaker = wav.parent.name
    if speaker not in speakers:
        continue
    # The first utterance ID is the spoken text; the ID after _ref_ is the prompt.
    match = re.fullmatch(
        rf"(?:cloned_)?{re.escape(speaker)}_((?:comma|wolf)_\d+)(?:_ref_(?:comma|wolf)_\d+_[^_]+)?",
        wav.stem,
    )
    if match is None:
        raise SystemExit(f"Unrecognized WAV filename: {wav}")
    transcript = raw_dir / "txt" / f"{match.group(1)}.txt"
    if not transcript.is_file():
        raise SystemExit(f"Missing transcript for {wav}: {transcript}")
    pairs.append((wav, transcript, temp_dir / "wav_txt_pairs" / speaker))

if not pairs:
    raise SystemExit(f"No WAV files found for the selected speakers in {raw_dir / 'wav'}")

for wav, transcript, destination in pairs:
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(wav, destination / wav.name)
    shutil.copy2(transcript, destination / f"{wav.stem}.txt")
print(f"Prepared {len(pairs)} WAV/transcript pairs in {temp_dir / 'wav_txt_pairs'}")
