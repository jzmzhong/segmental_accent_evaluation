"""Build subword summaries and Spearman heatmaps for objective metrics and annotations.

Adapted from data_analysis/Prolific/105_rpt_objective_correlation.py and
111_subword_correlation_heatmap.py (the generator of the original
word-level_metrics/subword_metric_rating_spearman_correlation_all.png).
"""

import argparse
import json
import os
from pathlib import Path
import re

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
TEMP_DIR = SCRIPT_DIR.parent / "data_temp"
os.environ.setdefault("MPLCONFIGDIR", str(TEMP_DIR / "models" / "matplotlib"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


SPEAKER_LABELS = {
    "6a08fea524e9dc84ff9a258a": "Australian male",
    "69e8b0adf78ba4d3ede8b1f5": "Australian female",
    "66fc6008cda3d277a8978dbf": "Scottish female",
    "69f8709095bf5e9416de1057": "Scottish male",
}

FEATURE_NAMES = ["ppg", "f0", "formants", "ecapatdnn", "wavlm", "genaid", "voxlect"]
RATING_COLUMNS = ["annotation_score"]

DISPLAY_NAMES = {
    "annotation_score": "S-ACC-Anno.",
    "ppg": "O-PPG Distance ",
    "f0": "O-F0 Distance",
    "formants": "O-Formants Distance",
    "ecapatdnn": "O-SPK (ECAPA-TDNN)",
    "wavlm": "O-SPK (WavLM-SV)",
    "genaid": "O-ACC (GenAID)",
    "voxlect": "O-ACC (Voxlect)",
}


def load_subword_metrics(data_dir, stat):
    frames = []
    direct_path = data_dir / f"subword_metric_summary_{stat}.csv"
    paths = [direct_path] if direct_path.is_file() else sorted(data_dir.glob(f"*/subword_metric_summary_{stat}.csv"))
    for csv_path in paths:
        data = pd.read_csv(csv_path)
        data = data.rename(columns={f"{feature}_distance_{stat}": feature for feature in FEATURE_NAMES})
        frames.append(data)
    if not frames:
        if stat == "midpoint":
            return load_subword_metrics(data_dir, "centroid")
        raise FileNotFoundError(f"No subword_metric_summary_{stat}.csv files found under {data_dir}")
    return pd.concat(frames, ignore_index=True)


def plot_correlation_heatmap(correlation, title, output_path):
    figure, axis = plt.subplots(figsize=(7, 6))
    sns.heatmap(
        correlation, annot=True, fmt=".2f", cmap="coolwarm", vmin=-1, vmax=1,
        square=True, ax=axis, cbar_kws={"label": "Spearman r"},
    )
    axis.set_title(title)
    axis.tick_params(axis="x", rotation=45)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def correlate(data, metric_columns):
    return data[metric_columns].astype(float).corr(method="spearman")


def format_latex_cell(value):
    if pd.isna(value):
        return ""
    color = "red" if value >= 0 else "blue"
    intensity = min(abs(value) * 100, 100)
    return f"\\cellcolor{{{color}!{intensity:.0f}}}{value:.2f}"


def write_latex_table(correlations_by_stat, row_order, output_path):
    """Write a booktabs table with one column per subword aggregation statistic
    (mean/max/midpoint), showing each metric's correlation with the subword
    annotation score under that aggregation."""
    rating_column = RATING_COLUMNS[0]
    stats = list(correlations_by_stat)
    header = " & ".join(stat.capitalize() for stat in stats)
    lines = [
        "\\begin{tabular}{l" + "c" * len(stats) + "}",
        "\\toprule",
        f"Metric & {header} \\\\",
        "\\midrule",
    ]
    for row in row_order:
        cells = [
            format_latex_cell(correlations_by_stat[stat].loc[row, rating_column]) for stat in stats
        ]
        lines.append(f"{DISPLAY_NAMES.get(row, row)} & " + " & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    output_path.write_text("\n".join(lines) + "\n")


STATS = ("mean", "max", "midpoint")


def plot_summaries(data_dir, output_dir, stat, exclude_sparc=False, write_latex=False, features=FEATURE_NAMES, target_speakers=None):
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    def load_and_filter(stat_name):
        data = load_subword_metrics(data_dir, stat_name)
        if target_speakers:
            data = data[data["target_speaker"].isin(target_speakers)]
        if exclude_sparc:
            data = data[data["tts"] != "sparc"]
        if data.empty:
            raise ValueError("No subword rows remain after filtering.")
        return data

    subword_data = load_and_filter(stat)
    metric_columns = list(features) + RATING_COLUMNS
    row_order = RATING_COLUMNS + list(features)

    groups = [("all", "All speakers pooled", subword_data)]
    groups.extend(
        (speaker, SPEAKER_LABELS.get(speaker, speaker), speaker_data)
        for speaker, speaker_data in subword_data.groupby("target_speaker")
    )

    # loaded once regardless of the chosen --stat, so the LaTeX table can compare all three
    stat_data = {stat_name: load_and_filter(stat_name) for stat_name in STATS} if write_latex else {}

    for speaker, label, speaker_data in groups:
        correlation = correlate(speaker_data, metric_columns)

        correlation.to_csv(output_dir / f"subword_metric_rating_spearman_correlation_{speaker}.csv")
        plot_correlation_heatmap(
            correlation,
            f"Subword-level Spearman correlation: {label}",
            output_dir / f"subword_metric_rating_spearman_correlation_{speaker}.png",
        )
        if write_latex:
            correlations_by_stat = {}
            for stat_name, stat_subword_data in stat_data.items():
                stat_speaker_data = (
                    stat_subword_data if speaker == "all"
                    else stat_subword_data[stat_subword_data["target_speaker"] == speaker]
                )
                correlations_by_stat[stat_name] = correlate(stat_speaker_data, metric_columns)
            write_latex_table(
                correlations_by_stat, row_order,
                output_dir / f"subword_metric_rating_spearman_correlation_{speaker}.tex",
            )
        print(f"{label}: correlated {len(speaker_data)} subwords across {len(metric_columns)} metrics/ratings.")


FEATURE_SPECS = {
    "ppg": ("ppg_features.pt", "frame_distances"),
    "f0": ("f0_formants.pt", "f0_frame_distances"),
    "formants": ("f0_formants.pt", "formant_frame_distances"),
    "ecapatdnn": ("ecapatdnn_embeddings.pt", "frame_distances"),
    "wavlm": ("wavlm_embeddings.pt", "frame_distances"),
    "genaid": ("genaid_embeddings.pt", "frame_distances"),
    "voxlect": ("voxlect_embeddings.pt", "frame_distances"),
}
CANDIDATE_PATTERN = re.compile(
    r"cloned_(?P<speaker>[0-9a-f]+)_(?P<utterance>(?:comma|wolf)_\d{3})_"
    r"ref_(?:comma|wolf)_\d{3}_(?P<tts>maskgct|f5tts|sparc)$"
)


def normalise_text(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def annotation_scores(annotations, segment_count):
    """Fraction of retained raters selecting each original pipe-delimited index."""
    if annotations.empty:
        raise ValueError("No retained annotation rows.")
    votes = np.zeros(segment_count)
    for selection in annotations["annotation"].fillna(""):
        indices = set(int(index) for index in str(selection).split("|") if index)
        if any(index < 0 or index >= segment_count for index in indices):
            raise ValueError("Annotation index lies outside the segmented transcript.")
        for index in indices:
            votes[index] += 1
    return votes / len(annotations)


def read_alignments(path, segments):
    """Preserve annotation indices even when a segment has no valid timing."""
    expected = [(index, text) for index, text in enumerate(segments) if normalise_text(text)]
    rows = []
    with path.open() as handle:
        for line in handle:
            start, end, text, *_ = line.rstrip("\n").split("\t")
            rows.append((float(start), float(end), text))
    if len(rows) != len(expected):
        raise ValueError(f"Alignment has {len(rows)} subwords; transcript has {len(expected)}.")
    aligned = []
    for (index, text), (start, end, aligned_text) in zip(expected, rows):
        if normalise_text(text) != normalise_text(aligned_text):
            raise ValueError(f"Alignment/transcript mismatch: {aligned_text!r} vs {text!r}.")
        if start >= 0 and end > start:
            aligned.append((index, start, end, aligned_text))
    return aligned


def frame_times(frame_count, duration):
    """Infer the original pipeline's 10/20 ms frame grid, allowing rounding edges."""
    if frame_count < 1:
        raise ValueError("Empty frame distance sequence.")
    step = min((0.01, 0.02), key=lambda value: abs(duration / value - frame_count))
    if abs(duration / step - frame_count) > 2:
        raise ValueError(f"{frame_count} frames do not match a 10/20 ms grid for {duration:.3f}s.")
    return np.round((np.arange(frame_count) + 0.5) * step, 5)


def aggregate_subwords(values, times, alignments, statistic):
    results = []
    for _, start, end, _ in alignments:
        if statistic in ("midpoint", "centroid"):
            results.append(values[np.abs(times - (start + end) / 2).argmin()])
        else:
            selected = values[(times >= start) & (times <= end)]
            results.append(getattr(np, statistic)(selected) if len(selected) else np.nan)
    return results


def build_subword_summaries(args, statistics):
    import soundfile as sf
    import torch

    caches = {}
    for name in args.features:
        filename, _ = FEATURE_SPECS[name]
        path = args.feature_dir / filename
        if path not in caches:
            if not path.is_file():
                raise FileNotFoundError(f"Missing feature cache {path}; run 12_extract_features_subword.sh first.")
            caches[path] = torch.load(path, map_location="cpu", weights_only=True)
    utterances = {entry["id"]: entry["text"].split("|")
                  for entry in json.loads(args.segmented_text.read_text())}
    rows = {statistic: [] for statistic in statistics}
    skipped = []
    annotation_paths = sorted(args.annotation_dir.glob("*/*.csv"))
    if not annotation_paths:
        raise FileNotFoundError(f"No per-candidate annotation CSVs under {args.annotation_dir}.")
    for annotation_path in annotation_paths:
        audio_id = annotation_path.stem
        match = CANDIDATE_PATTERN.fullmatch(audio_id)
        if not match:
            continue
        speaker, utterance, tts = match.group("speaker", "utterance", "tts")
        if args.target_speakers and speaker not in args.target_speakers:
            continue
        if args.exclude_sparc and tts == "sparc":
            continue
        candidate = args.wav_dir / annotation_path.parent.name / speaker / f"{audio_id}.wav"
        alignment_path = args.alignment_dir / speaker / f"{audio_id}_aligned.txt"
        try:
            annotations = pd.read_csv(
                annotation_path, dtype={"TAR_SPK": str, "prolific_pid": str, "annotation": str}
            )
            annotations = annotations.loc[annotations["TAR_SPK"].eq(speaker)]
            if args.raters == "listeners":
                annotations = annotations.loc[annotations["rater_role"].eq("listener") &
                                              annotations["prolific_pid"].ne(speaker)]
            elif args.raters == "voice-donors":
                annotations = annotations.loc[annotations["prolific_pid"].eq(speaker)]
            segments = utterances[utterance]
            scores = annotation_scores(annotations, len(segments))
            alignments = read_alignments(alignment_path, segments)
            duration = sf.info(candidate).duration
            feature_values = {}
            feature_times = {}
            for name in args.features:
                filename, key = FEATURE_SPECS[name]
                entry = caches[args.feature_dir / filename].get(audio_id)
                if entry is None or entry.get(key) is None:
                    raise ValueError(f"Missing {name} frame distances for {audio_id}.")
                value = entry[key]
                value = value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)
                if value.ndim != 1:
                    raise ValueError(f"Expected a frame distance vector for {name}, got {value.shape}.")
                feature_values[name] = value
                feature_times[name] = frame_times(len(value), duration)
            for statistic in statistics:
                aggregated = {name: aggregate_subwords(values, feature_times[name], alignments, statistic)
                              for name, values in feature_values.items()}
                for aligned_index, (annotation_index, start, end, text) in enumerate(alignments):
                    rows[statistic].append({
                        "audio_id": audio_id, "target_speaker": speaker,
                        "utterance_id": utterance, "tts": tts,
                        "subword_index": annotation_index, "subword": text,
                        "start_seconds": start, "end_seconds": end,
                        "listener_count": len(annotations), "annotation_score": scores[annotation_index],
                        **{f"{name}_distance_{statistic}": values[aligned_index]
                           for name, values in aggregated.items()},
                    })
        except (FileNotFoundError, KeyError, ValueError, RuntimeError) as error:
            skipped.append({"audio_id": audio_id, "reason": str(error)})
            print(f"Skipping {audio_id}: {error}")
    args.summary_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(skipped, columns=["audio_id", "reason"]).to_csv(args.summary_dir / "skipped_candidates.csv", index=False)
    if not any(rows.values()):
        raise ValueError("No valid subwords. Check skipped_candidates.csv and run alignment/extraction first.")
    for statistic, values in rows.items():
        pd.DataFrame(values).to_csv(args.summary_dir / f"subword_metric_summary_{statistic}.csv", index=False)
        print(f"Wrote {len(values)} subwords ({statistic}); {len(skipped)} candidates skipped.")


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-dir", "--data-dir", type=Path,
                        help="Read existing summaries instead of building them (also supports old per-batch results).")
    parser.add_argument("--feature-dir", type=Path, default=TEMP_DIR / "features")
    parser.add_argument("--alignment-dir", type=Path, default=TEMP_DIR / "wav_txt_pairs_g2psubword")
    parser.add_argument("--annotation-dir", type=Path, default=DATA_DIR / "annotations_ratings")
    parser.add_argument("--wav-dir", type=Path, default=DATA_DIR / "wav")
    parser.add_argument("--segmented-text", type=Path, default=DATA_DIR / "utterances_segmented.json")
    parser.add_argument("--output-dir", type=Path, default=SCRIPT_DIR.parent / "results" / "word-level_metrics")
    parser.add_argument("--features", nargs="+", choices=FEATURE_NAMES, default=FEATURE_NAMES)
    parser.add_argument("--target-speakers", nargs="+", default=list(SPEAKER_LABELS))
    parser.add_argument("--raters", choices=("all", "listeners", "voice-donors"), default="all",
                        help="Raters used when building scores; all reproduces the original pipeline (default).")
    parser.add_argument("--stat", choices=(*STATS, "centroid"), default="max",
                        help="Subword aggregation: max (default), mean, or nearest frame to the midpoint; centroid is a legacy alias.")
    parser.add_argument("--exclude-sparc", action="store_true")
    parser.add_argument("--latex", action="store_true", help="Also compare mean/max/midpoint in LaTeX tables.")
    args = parser.parse_args()
    if args.stat == "centroid":
        args.stat = "midpoint"
    if args.summary_dir is None:
        args.summary_dir = TEMP_DIR / "subword_metrics"
        build_subword_summaries(args, STATS if args.latex else (args.stat,))
    plot_summaries(args.summary_dir, args.output_dir, args.stat, args.exclude_sparc,
                   args.latex, args.features, args.target_speakers)


if __name__ == "__main__":
    cli()
