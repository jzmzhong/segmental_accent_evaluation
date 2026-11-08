# Subjective–objective correlation

Run commands from this directory.

```bash
# Align audio to subwords using the existing Conda mfa environment.
bash 01_mfa_align.sh
uv run python 02_g2p_align_subword.py

# Install Python dependencies and download models (once).
uv sync
bash 11_model_setup.sh

# Extract frame features for subword analysis.
bash 12_extract_features_frame.sh

# Extract utterance features directly from audio (no step 12 or frame caches needed).
bash 13_extract_features_utterance.sh

# Subword-level correlation between objective features and subjective annotations.
bash 21_correlation_subword.sh --raters listeners --method spearman

# Utterance-level correlation between objective features and subjective annotations.
bash 22_correlation_utterance.sh --raters listeners --method spearman
```

For aggregating frame-level metrics into subword-level for correlation analysis, **maximum frame distance within each subword** is used by default.
Other options are the mean or the frame nearest the temporal midpoint:

