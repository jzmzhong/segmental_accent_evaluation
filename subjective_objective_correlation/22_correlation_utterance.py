"""Build utterance-level summaries and Spearman heatmaps for objective metrics and subjective annotations."""

import argparse
import json
import os
from pathlib import Path
import re

from extraction_common import UTTERANCE_CACHE_FILENAMES, load_cache

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

RATING_COLUMNS = ["Annotated Subwords", "Accent SMOS", "Speaker SMOS"]

# These columns measure similarity (higher = more similar); everything else measures
# distance (higher = more different), so distances are negated before correlating.
SIMILARITY_COLUMNS = {"Accent SMOS", "Speaker SMOS"}
COSINE_DISTANCE_COLUMNS = {"ecapatdnn_cosine", "wavlm_cosine", "genaid_cosine", "voxlect_cosine"}

DISPLAY_NAMES = {
    "Annotated Subwords": "S-ACC-Anno.",
    "Accent SMOS": "S-ACC-SMOS",
    "Speaker SMOS": "S-SPK-SMOS",
    "ppg_dtw_jsd": "O-PPG Distance ",
    "f0_dtw_rmse": "O-F0 Distance",
    "formant_dtw_rmse": "O-Formants Distance",
    "ecapatdnn_cosine": "O-SPK (ECAPA-TDNN)",
    "wavlm_cosine": "O-SPK (WavLM-SV)",
    "genaid_cosine": "O-ACC (GenAID)",
    "voxlect_cosine": "O-ACC (Voxlect)",
}


def plot_correlation_heatmap(correlation, title, method, output_path):
    figure, axis = plt.subplots(figsize=(9, 8))
    sns.heatmap(
        correlation, annot=True, fmt=".2f", cmap="coolwarm", vmin=-1, vmax=1,
        square=True, ax=axis, cbar_kws={"label": f"{method.capitalize()} r"},
    )
    axis.set_title(title)
    axis.tick_params(axis="x", rotation=45)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def correlate(data, metric_columns, method):
    correlation_data = data[metric_columns].astype(float)
    cosine_distance_columns = [column for column in metric_columns if column in COSINE_DISTANCE_COLUMNS]
    correlation_data[cosine_distance_columns] = 1.-correlation_data[cosine_distance_columns]

    other_distance_columns = [column for column in metric_columns if column not in SIMILARITY_COLUMNS and column not in COSINE_DISTANCE_COLUMNS]
    correlation_data[other_distance_columns] = -correlation_data[other_distance_columns]

    return correlation_data.corr(method=method)


def format_latex_cell(value):
    if pd.isna(value):
        return ""
    color = "red" if value >= 0 else "blue"
    intensity = min(abs(value) * 100, 100)
    return f"\\cellcolor{{{color}!{intensity:.0f}}}{value:.2f}"


def write_latex_table(correlation, rating_columns, row_order, output_path):
    """Write a booktabs table: columns=subjective ratings, rows=all metrics/ratings.
    The subjective-vs-subjective block only fills its lower triangle, since the
    correlation matrix is symmetric."""
    header = " & ".join(DISPLAY_NAMES.get(column, column) for column in rating_columns)
    lines = [
        "\\begin{tabular}{l" + "c" * len(rating_columns) + "}",
        "\\toprule",
        f"Metric & {header} \\\\",
        "\\midrule",
    ]
    for row_index, row in enumerate(row_order):
        cells = []
        for column in rating_columns:
            if row in rating_columns and rating_columns.index(column) > rating_columns.index(row):
                cells.append("")
            else:
                cells.append(format_latex_cell(correlation.loc[row, column]))
        lines.append(f"{DISPLAY_NAMES.get(row, row)} & " + " & ".join(cells) + " \\\\")
        if row_index == len(rating_columns) - 1:
            lines.append("\\midrule")
    lines += ["\\bottomrule", "\\end{tabular}"]
    output_path.write_text("\n".join(lines) + "\n")


FEATURE_SPECS = {
    "f0": ("f0_formants", "f0_distance", "f0_dtw_rmse"),
    "formants": ("f0_formants", "formant_distance", "formant_dtw_rmse"),
    "ppg": ("ppg", "distance", "ppg_dtw_jsd"),
    "ecapatdnn": ("ecapatdnn", "distance", "ecapatdnn_cosine"),
    "wavlm": ("wavlm", "distance", "wavlm_cosine"),
    "genaid": ("genaid", "distance", "genaid_cosine"),
    "voxlect": ("voxlect", "distance", "voxlect_cosine"),
}
CANDIDATE_PATTERN = re.compile(
    r"cloned_(?P<speaker>[0-9a-f]+)_(?P<utterance>(?:comma|wolf)_\d{3})_"
    r"ref_(?:comma|wolf)_\d{3}_(?P<tts>maskgct|f5tts|sparc)$"
)


def load_subword_counts(path):
    return {entry["id"]: sum(bool(re.sub(r"[^a-z0-9]", "", segment.lower()))
                             for segment in entry["text"].split("|"))
            for entry in json.loads(Path(path).read_text())}


def subjective_scores(annotations, subword_count, raw_counts=False):
    """Average ratings over retained respondents, counting empty selections as zero."""
    if annotations.empty:
        raise ValueError("No retained annotation rows.")
    if "annotated_subword_count" in annotations:
        counts = pd.to_numeric(annotations["annotated_subword_count"], errors="raise")
    else:
        counts = annotations["annotation"].fillna("").map(
            lambda value: len({index for index in str(value).split("|") if index}))
    if not raw_counts and subword_count <= 0:
        raise ValueError("No annotatable subwords in the transcript.")
    return {
        "Annotated Subwords": float(counts.mean()) if raw_counts else float(counts.mean() / subword_count * 100),
        "Accent SMOS": float(pd.to_numeric(annotations["accent_smos"], errors="raise").mean()),
        "Speaker SMOS": float(pd.to_numeric(annotations["speaker_smos"], errors="raise").mean()),
    }


def build_utterance_summary(args):
    caches = {}
    for name in args.features:
        model, _, _ = FEATURE_SPECS[name]
        if model not in caches:
            path = args.feature_dir / UTTERANCE_CACHE_FILENAMES[model]
            if not path.is_file():
                raise FileNotFoundError(f"Missing utterance cache {path}; run 13_extract_features_utterance.sh first.")
            caches[model] = load_cache(path)
    subword_counts = load_subword_counts(args.segmented_text)
    paths = sorted(args.annotation_dir.glob("*/*.csv"))
    if not paths:
        raise FileNotFoundError(f"No per-candidate annotation CSVs under {args.annotation_dir}.")
    rows, skipped = [], []
    for path in paths:
        match = CANDIDATE_PATTERN.fullmatch(path.stem)
        if match is None:
            continue
        speaker, utterance, tts = match.group("speaker", "utterance", "tts")
        if args.target_speakers and speaker not in args.target_speakers:
            continue
        if (args.exclude_sparc and tts == "sparc") or (args.only_sparc and tts != "sparc"):
            continue
        try:
            annotations = pd.read_csv(path, dtype={"TAR_SPK": str, "prolific_pid": str, "annotation": str})
            annotations = annotations.loc[annotations["TAR_SPK"].eq(speaker)]
            if args.raters == "listeners":
                annotations = annotations.loc[annotations["rater_role"].eq("listener") &
                                              annotations["prolific_pid"].ne(speaker)]
            elif args.raters == "voice-donors":
                annotations = annotations.loc[annotations["prolific_pid"].eq(speaker)]
            subjective = subjective_scores(annotations, subword_counts[utterance], args.raw_annotated_subwords)
            objective = {}
            for name in args.features:
                model, key, column = FEATURE_SPECS[name]
                entry = caches[model].get(path.stem)
                if entry is None or entry.get(key) is None:
                    raise ValueError(f"Missing {name} utterance distance for {path.stem}.")
                value = entry[key]
                if hasattr(value, "numel") and value.numel() != 1:
                    raise ValueError(f"Expected scalar {name} distance.")
                objective[column] = float(value)
            rows.append({"audio_id": path.stem, "target_speaker": speaker,
                         "utterance": f"{utterance}_{tts}", "utterance_id": utterance,
                         "tts": tts, "listener_count": len(annotations), **objective, **subjective})
        except (KeyError, ValueError, RuntimeError) as error:
            skipped.append({"audio_id": path.stem, "reason": str(error)})
            print(f"Skipping {path.stem}: {error}")
    args.summary_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(skipped, columns=["audio_id", "reason"]).to_csv(args.summary_dir / "skipped_candidates.csv", index=False)
    if not rows:
        raise ValueError("No valid utterances. Check skipped_candidates.csv and run step 13 first.")
    data = pd.DataFrame(rows)
    data.to_csv(args.summary_dir / "utterance_metric_summary.csv", index=False)
    print(f"Wrote {len(data)} utterances; {len(skipped)} candidates skipped.")
    return data


def plot_summaries(summary_dir, output_dir, features, target_speakers=None,
                   exclude_sparc=False, only_sparc=False, write_latex=False, method="spearman"):
    data = pd.read_csv(Path(summary_dir) / "utterance_metric_summary.csv", dtype={"target_speaker": str})
    if target_speakers:
        data = data[data["target_speaker"].isin(target_speakers)]
    if exclude_sparc:
        data = data[data["tts"] != "sparc"]
    if only_sparc:
        data = data[data["tts"] == "sparc"]
    if data.empty:
        raise ValueError("No utterances remain after filtering.")
    metric_columns = [FEATURE_SPECS[name][2] for name in features] + RATING_COLUMNS
    row_order = RATING_COLUMNS + [FEATURE_SPECS[name][2] for name in features]
    groups = [("all", "All speakers pooled", data)]
    groups.extend((speaker, SPEAKER_LABELS.get(speaker, speaker), rows)
                  for speaker, rows in data.groupby("target_speaker"))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for speaker, label, rows in groups:
        correlation = correlate(rows, metric_columns, method)
        stem = f"utterance_metric_rating_{method}_correlation_{speaker}"
        correlation.to_csv(output_dir / f"{stem}.csv")
        plot_correlation_heatmap(correlation, f"Utterance-level {method.capitalize()} correlation: {label}",
                                 method, output_dir / f"{stem}.png")
        if write_latex:
            write_latex_table(correlation, RATING_COLUMNS, row_order, output_dir / f"{stem}.tex")
        print(f"{label}: correlated {len(rows)} utterances across {len(metric_columns)} metrics/ratings.")


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-dir", type=Path, help="Read an existing utterance_metric_summary.csv instead of building it.")
    parser.add_argument("--feature-dir", type=Path, default=TEMP_DIR / "features_utterance")
    parser.add_argument("--annotation-dir", type=Path, default=DATA_DIR / "annotations_ratings")
    parser.add_argument("--segmented-text", type=Path, default=DATA_DIR / "utterances_segmented.json")
    parser.add_argument("--output-dir", type=Path, default=SCRIPT_DIR.parent / "results" / "utterance-level_metrics")
    parser.add_argument("--features", nargs="+", choices=tuple(FEATURE_SPECS), default=tuple(FEATURE_SPECS))
    parser.add_argument("--target-speakers", nargs="+", default=list(SPEAKER_LABELS))
    parser.add_argument("--raters", choices=("all", "listeners", "voice-donors"), default="all")
    parser.add_argument("--method", choices=("spearman", "pearson"), default="spearman")
    systems = parser.add_mutually_exclusive_group()
    systems.add_argument("--exclude-sparc", action="store_true")
    systems.add_argument("--only-sparc", action="store_true")
    parser.add_argument("--raw-annotated-subwords", action="store_true", help="Use mean counts instead of annotated-subword percentages.")
    parser.add_argument("--latex", action="store_true")
    args = parser.parse_args()
    if args.summary_dir is None:
        args.summary_dir = TEMP_DIR / "utterance_metrics"
        build_utterance_summary(args)
    plot_summaries(args.summary_dir, args.output_dir, args.features, args.target_speakers,
                   args.exclude_sparc, args.only_sparc, args.latex, args.method)


if __name__ == "__main__":
    cli()
