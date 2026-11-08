"""Select rated comma_001–comma_020 candidates and their original recordings."""

import csv
from pathlib import Path
import re

TARGET_SPEAKERS = {
    "69e8b0adf78ba4d3ede8b1f5", "6a08fea524e9dc84ff9a258a",
    "66fc6008cda3d277a8978dbf", "69f8709095bf5e9416de1057",
}
CANDIDATE_PATTERN = re.compile(
    r"cloned_(?P<speaker>[0-9a-f]+)_(?P<utterance>comma_(?:00[1-9]|01[0-9]|020))_"
    r"ref_(?:comma|wolf)_\d{3}_(?:f5tts|maskgct|sparc)$"
)


def selected_stems(annotation_dir, speakers=TARGET_SPEAKERS):
    """Include rated generations plus same-utterance originals, not synthesis prompts.

    An empty annotation selection is a valid rating; require a CSV response row,
    not a nonempty selection of subword indices.
    """
    selected = set()
    for path in sorted(Path(annotation_dir).glob("*/*.csv")):
        match = CANDIDATE_PATTERN.fullmatch(path.stem)
        if match is None:
            continue
        speaker, utterance = match.group("speaker", "utterance")
        if speakers is not None and speaker not in speakers:
            continue
        with path.open(newline="") as handle:
            rows = csv.DictReader(handle)
            if not rows.fieldnames or "annotation" not in rows.fieldnames:
                continue
            if not any(row.get("TAR_SPK") == speaker for row in rows):
                continue
        selected.update((path.stem, f"{speaker}_{utterance}"))
    if not selected:
        raise ValueError(f"No annotated comma_001–comma_020 recordings found under {annotation_dir}.")
    return selected
