"""Extract utterance-level PPG, accent, speaker, and F0/formant features for utterance-level analysis."""

import argparse
from pathlib import Path

import numpy as np

from distances import cosine_distance, dtw_alignment
from model_setup import configure_caches as configure_model_caches

from extraction_common import (
    UTTERANCE_CACHE_FILENAMES as CACHE_FILENAMES,
    DEFAULT_SPEAKERS, TEMP_DIR, candidate_pairs, load_cache,
)


def as_frames(value):
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    value = np.asarray(value)
    if value.ndim != 2 or 0 in value.shape:
        raise ValueError(f"Expected nonempty 2D frame features, got {value.shape}.")
    return value


def pool_frames(name, frames, genaid_pool=None):
    """Return a pooled accent vector shaped (1, dimensions)."""
    frames = as_frames(frames)
    if name == "voxlect":
        return frames.mean(axis=0, keepdims=True)
    if name == "genaid":
        if genaid_pool is None:
            raise ValueError("GenAID requires its trained pooling/MLP head.")
        return genaid_pool(frames)
    raise ValueError(f"No frame pooling method for {name}.")


def cache_entry(name, reference, candidate, method):
    import torch

    reference, candidate = np.asarray(reference), np.asarray(candidate)
    entry = {"reference_embeddings": torch.as_tensor(reference).cpu(),
             "candidate_embeddings": torch.as_tensor(candidate).cpu(), "method": method}
    if name == "ppg":
        # Align complete sequences, then omit steps with predicted silence
        # (phone ID 39) on either side from both the cost and denominator.
        _, cost, path = dtw_alignment(reference.T, candidate.T, metric="jensenshannon")
        speech = ((reference.argmax(axis=0)[path[0]] != 39) &
                  (candidate.argmax(axis=0)[path[1]] != 39))
        values = cost[path[0], path[1]][speech]
        entry["distance"] = float(values.mean()) if len(values) else float("nan")
        entry["alignment_steps"] = len(path[0])
        entry["scored_alignment_steps"] = len(values)
    elif name == "f0_formants":
        distance, _, path = dtw_alignment(reference, candidate, metric="rmse")
        ref, cand = reference[path[0]], candidate[path[1]]
        entry["distance"] = distance
        entry["f0_distance"] = float(np.abs(ref[:, 0] - cand[:, 0]).mean())
        entry["formant_distance"] = float(np.sqrt(np.mean((ref[:, 1:] - cand[:, 1:]) ** 2, axis=1)).mean())
        entry["alignment_steps"] = len(path[0])
    else:
        entry["distance"] = cosine_distance(reference[0], candidate[0])
    return entry


def extract_recording(name, path, model=None, gpu=None):
    """Extract one recording directly from audio; no frame cache is read."""
    if name in ("wavlm", "ecapatdnn", "genaid"):
        model_name = "ecapa" if name == "ecapatdnn" else name
        result = getattr(model, f"extract_{model_name}_utterance")(path)
        if name in ("wavlm", "ecapatdnn"):
            norms = np.linalg.norm(result, axis=-1, keepdims=True)
            result = result / np.maximum(norms, np.finfo(np.float32).eps)
        return result
    if name == "f0_formants":
        from f0_formants import extract_f0_formants
        return as_frames(extract_f0_formants(path, interpolate=False))
    if name == "ppg":
        import ppgs
        frames = ppgs.from_audio(ppgs.load.audio(str(path)), ppgs.SAMPLE_RATE,
                                gpu=None if gpu == -1 else gpu).squeeze(0).float().cpu().numpy()
        return as_frames(frames)
    return pool_frames(name, model.extract_voxlect_frame(path))


def extract_features(target_speakers=DEFAULT_SPEAKERS, models=tuple(CACHE_FILENAMES), *,
                     wav_dir=TEMP_DIR / "wav_txt_pairs", cache_dir=TEMP_DIR / "features_utterance",
                     model_dir=TEMP_DIR / "models", device=None, gpu=None,
                     genaid_source=None, voxlect_repo=None):
    from functools import partial

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
        elif name in ("wavlm", "ecapatdnn"):
            from speaker_similarity import SpeakerSimilarity
            model = SpeakerSimilarity("ecapa" if name == "ecapatdnn" else name,
                                      device=device, savedir=model_dir, utterance_only=True)
        else:
            model = None
        extract = partial(extract_recording, name, model=model, gpu=gpu)
        method = {"ppg": "dtw_jensenshannon_per_speech_alignment_step", "voxlect": "mean_valid_frames",
                  "genaid": "native_pooling_mlp", "f0_formants": "dtw_rmse_per_alignment_step",
                  "wavlm": "native_xvector_l2", "ecapatdnn": "native_ecapa_l2"}[name]
        embeddings = {}  # Reuse originals shared by multiple candidates.
        try:
            for reference, candidate in pending:
                try:
                    for path in (reference, candidate):
                        if path not in embeddings:
                            embeddings[path] = extract(path)
                    cache[candidate.stem] = cache_entry(name, embeddings[reference], embeddings[candidate], method)
                    print(f"Extracted utterance {name}: {candidate.stem} ({method})")
                except (IndexError, RuntimeError, ValueError) as error:
                    print(f"Skipping {candidate.stem} ({name}): {error}")
        finally:
            # Save completed entries even if a later pair fails or extraction is interrupted.
            temporary_path = cache_path.with_suffix(".tmp")
            torch.save(cache, temporary_path)
            temporary_path.replace(cache_path)
        del extract, model, embeddings
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav-dir", type=Path, default=TEMP_DIR / "wav_txt_pairs")
    parser.add_argument("--cache-dir", type=Path, default=TEMP_DIR / "features_utterance")
    parser.add_argument("--model-dir", type=Path, default=TEMP_DIR / "models")
    parser.add_argument("--models", nargs="+", choices=tuple(CACHE_FILENAMES), default=tuple(CACHE_FILENAMES))
    parser.add_argument("--target-speakers", nargs="+", default=DEFAULT_SPEAKERS)
    parser.add_argument("--all-speakers", action="store_true", help="Process every speaker instead of the four target speakers.")
    parser.add_argument("--device", help="Device for accent/speaker models, e.g. cpu or cuda:0 (default: automatic).")
    parser.add_argument("--gpu", type=int, default=None, help="PPG GPU index; -1 selects CPU (default: CPU).")
    parser.add_argument("--genaid-source", help="GenAID repository ID or local model directory (default: jzmzhong/accent-id-genaid).")
    parser.add_argument("--voxlect-repo", type=Path, help="Voxlect repository containing src/model/dialect/whisper_dialect.py.")
    args = parser.parse_args()
    extract_features(target_speakers=None if args.all_speakers else args.target_speakers,
                     models=args.models, wav_dir=args.wav_dir, cache_dir=args.cache_dir,
                     model_dir=args.model_dir, device=args.device,
                     gpu=None if args.gpu == -1 else args.gpu,
                     genaid_source=args.genaid_source, voxlect_repo=args.voxlect_repo)


if __name__ == "__main__":
    main()
