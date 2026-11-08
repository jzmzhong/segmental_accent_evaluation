"""Extract frame-level PPG, accent, speaker, and F0/formant features for subword analysis.
"""

import argparse
from pathlib import Path
import re

from model_setup import configure_caches as configure_model_caches

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
TEMP_DIR = SCRIPT_DIR.parent / "data_temp"
DEFAULT_SPEAKERS = (
    "69e8b0adf78ba4d3ede8b1f5", "6a08fea524e9dc84ff9a258a",
    "66fc6008cda3d277a8978dbf", "69f8709095bf5e9416de1057",
)
CACHE_FILENAMES = {
    "ppg": "ppg_features.pt",
    "genaid": "genaid_embeddings.pt",
    "voxlect": "voxlect_embeddings.pt",
    "f0_formants": "f0_formants.pt",
    "wavlm": "wavlm_embeddings.pt",
    "ecapatdnn": "ecapatdnn_embeddings.pt",
}
CANDIDATE_PATTERN = re.compile(
    r"cloned_(?P<speaker>[0-9a-f]+)_(?P<utterance>(?:comma|wolf)_\d{3})_"
    r"ref_(?:comma|wolf)_\d{3}_(?:maskgct|f5tts|sparc)$"
)


def load_cache(path):
    import torch
    return torch.load(path, map_location="cpu", weights_only=True) if path.exists() else {}


def cache_entry(result, f0_formants=False):
    import torch
    if f0_formants:
        f0_result, formant_result, reference, candidate = result
        values = {"f0_frame_distances": f0_result[2], "formant_frame_distances": formant_result[2]}
    else:
        _, _, candidate_values, reference, candidate = result
        values = {"frame_distances": candidate_values}
    values.update(reference_embeddings=reference, candidate_embeddings=candidate)
    return {key: torch.as_tensor(value) if value is not None else None for key, value in values.items()}


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


def extract_features(target_speakers=DEFAULT_SPEAKERS, models=tuple(CACHE_FILENAMES), *,
                     wav_dir=TEMP_DIR / "wav_txt_pairs", cache_dir=TEMP_DIR / "features",
                     model_dir=TEMP_DIR / "models", device=None, gpu=None,
                     genaid_source=None, voxlect_repo=None):
    wav_dir, cache_dir, model_dir = map(lambda p: Path(p).expanduser().resolve(), (wav_dir, cache_dir, model_dir))
    if not wav_dir.is_dir():
        raise FileNotFoundError(f"Audio directory does not exist: {wav_dir}")
    unknown = set(models) - CACHE_FILENAMES.keys()
    if unknown:
        raise ValueError(f"Unknown feature models: {sorted(unknown)}")
    configure_model_caches(model_dir)
    import torch

    cache_dir.mkdir(parents=True, exist_ok=True)
    pairs = list(candidate_pairs(wav_dir, target_speakers))
    if not pairs:
        raise ValueError(f"No candidate/reference pairs found in {wav_dir} for the selected speakers.")
    for name in models:
        cache_path = cache_dir / CACHE_FILENAMES[name]
        cache = load_cache(cache_path)
        pending = [(ref, cand) for ref, cand in pairs if cand.stem not in cache]
        if not pending:
            print(f"{name}: all {len(pairs)} pairs already cached.")
            continue
        # Load one model at a time to limit GPU memory use.
        if name in ("genaid", "voxlect"):
            from accent_similarity import AccentSimilarity
            model = AccentSimilarity(name, device=device, cache_dir=model_dir,
                                     genaid_source=genaid_source, voxlect_repo=voxlect_repo)
            compare = model.compute_similarity
        elif name in ("wavlm", "ecapatdnn"):
            from speaker_similarity import SpeakerSimilarity
            model = SpeakerSimilarity("ecapa" if name == "ecapatdnn" else name,
                                      device=device, savedir=model_dir)
            compare = model.compute_similarity
        elif name == "ppg":
            from functools import partial
            from ppg_distance import extract_ppgs
            model = None
            compare = partial(extract_ppgs, distance_metric="jensenshannon", remove_silence=False, gpu=gpu)
        else:
            from f0_formants import compute_similarity
            model = None
            compare = compute_similarity
        try:
            for reference, candidate in pending:
                try:
                    result = compare(reference, candidate, return_embeddings=True)
                    cache[candidate.stem] = cache_entry(result, f0_formants=name == "f0_formants")
                    print(f"Extracted {name}: {candidate.stem}")
                except (IndexError, RuntimeError, ValueError) as error:
                    print(f"Skipping {candidate.stem} ({name}): {error}")
        finally:
            # Save completed entries even if a later pair fails or extraction is interrupted.
            temporary_path = cache_path.with_suffix(".tmp")
            torch.save(cache, temporary_path)
            temporary_path.replace(cache_path)
        del compare, model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav-dir", type=Path, default=TEMP_DIR / "wav_txt_pairs")
    parser.add_argument("--cache-dir", type=Path, default=TEMP_DIR / "features")
    parser.add_argument("--model-dir", type=Path, default=TEMP_DIR / "models")
    parser.add_argument("--target-speakers", nargs="+", default=DEFAULT_SPEAKERS)
    parser.add_argument("--all-speakers", action="store_true", help="Process every speaker instead of the four target speakers.")
    parser.add_argument("--models", nargs="+", choices=tuple(CACHE_FILENAMES), default=tuple(CACHE_FILENAMES))
    parser.add_argument("--device", help="Device for accent/speaker models, e.g. cpu or cuda:0 (default: automatic).")
    parser.add_argument("--gpu", type=int, default=None, help="PPG GPU index; -1 selects CPU (default: CPU).")
    parser.add_argument("--genaid-source",
                        help="GenAID repository ID or local model directory (default: jzmzhong/accent-id-genaid).")
    parser.add_argument("--voxlect-repo", type=Path, help="Voxlect repository containing src/model/dialect/whisper_dialect.py.")
    args = parser.parse_args()
    extract_features(target_speakers=None if args.all_speakers else args.target_speakers,
                     models=args.models, wav_dir=args.wav_dir, cache_dir=args.cache_dir,
                     model_dir=args.model_dir, device=args.device,
                     gpu=None if args.gpu == -1 else args.gpu,
                     genaid_source=args.genaid_source, voxlect_repo=args.voxlect_repo)


if __name__ == "__main__":
    main()
