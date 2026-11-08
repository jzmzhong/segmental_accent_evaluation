# Segmental Accent Evaluation

This repository contains tools used in the paper [Beyond Utterance-Level Speaker Similarity: Perception-Aligned Segmental Evaluation of Accent in Speech Generation](https://arxiv.org/abs/2610.37912).

The recordings, generated speech, ratings, and segmental annotations are available on [Hugging Face](https://huggingface.co/datasets/jzmzhong/segmental_accent_annotation). Explore visualizations of the ratings, annotations, and their relationships with objective metrics in the [interactive results viewer](https://jzmzhong.github.io/Segmental-Accent-Evaluation/results.html).

## Recording and Evaluation Interface

[`recording_evaluation_interface/`](./recording_evaluation_interface/) contains two interfaces for data collection:

1. **Voice recording**: participants read the selected utterances aloud and complete a demographic survey.
2. **Accent evaluation**: participants rate speech generated in their own voice (own-voice evaluation), or listeners from the same accent region rate it (stranger-voice evaluation). Raters mark the subwords that sound off-accent.

See the [interface README](./recording_evaluation_interface/README.md) for setup, local testing, and data formats.

## Subjective–Objective Correlation

[`subjective_objective_correlation/`](./subjective_objective_correlation/) correlates the subjective annotations with objective metrics, at the subword and utterance levels:

1. **Alignment** (`01`–`02`): force-align the audio with Montreal Forced Aligner, then map the phones to the annotated subwords.
2. **Feature extraction** (`11`–`13`): compute frame-level and utterance-level distances from PPG, F0, formants, speaker embeddings (ECAPA-TDNN, WavLM-SV), and accent embeddings (GenAID, Voxlect).
3. **Correlation** (`21`–`22`): compute Spearman correlations with the subjective scores and output heatmaps and optional LaTeX tables.

See the [correlation README](./subjective_objective_correlation/README.md) for commands and options.
