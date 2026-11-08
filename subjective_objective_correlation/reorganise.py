#!/usr/bin/env python3
"""Prepare only rated comma_001–comma_020 candidates and their originals.

Usage: python reorganise.py RAW_DATA_DIR DATA_TEMP_DIR
"""

from pathlib import Path
import shutil
import sys

from selection import selected_stems


def reorganise(raw_dir, temp_dir):
    raw_dir, temp_dir = Path(raw_dir), Path(temp_dir)
    selected = selected_stems(raw_dir / "annotations_ratings")
    pairs = []
    for wav in sorted((raw_dir / "wav").rglob("*.wav")):
        if wav.stem not in selected:
            continue
        speaker = wav.parent.name
        utterance = wav.stem.removeprefix("cloned_").removeprefix(f"{speaker}_").split("_ref_")[0]
        transcript = raw_dir / "txt" / f"{utterance}.txt"
        if not transcript.is_file():
            raise FileNotFoundError(f"Missing transcript: {transcript}")
        pairs.append((wav, transcript, temp_dir / "wav_txt_pairs" / speaker))
    missing = selected - {wav.stem for wav, _, _ in pairs}
    if missing:
        raise FileNotFoundError(f"Selected recordings missing from {raw_dir / 'wav'}: {sorted(missing)}")

    # Synchronize only the derived MFA corpus; leave source data untouched.
    corpus = temp_dir / "wav_txt_pairs"
    expected = {destination / f"{wav.stem}{suffix}"
                for wav, _, destination in pairs for suffix in (".wav", ".txt")}
    removed = 0
    for existing in corpus.rglob("*"):
        if existing.is_file() and existing.suffix in (".wav", ".txt") and existing not in expected:
            existing.unlink()
            removed += 1
    for wav, transcript, destination in pairs:
        destination.mkdir(parents=True, exist_ok=True)
        for source, target in ((wav, destination / wav.name),
                               (transcript, destination / f"{wav.stem}.txt")):
            if not target.exists() or source.stat().st_size != target.stat().st_size or source.stat().st_mtime > target.stat().st_mtime:
                shutil.copy2(source, target)
    print(f"Prepared {len(pairs)} rated/reference WAV–TXT pairs in {corpus}; removed {removed} stale derived files.")


if __name__ == "__main__":
    reorganise(*sys.argv[1:])
