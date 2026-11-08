# Subjective–objective correlation

Run commands from this directory.

```bash
# Install Python dependencies and download models (once).
uv sync
bash 11_model_setup.sh

# Align audio to subwords using an existing Conda mfa environment.
bash 01_mfa_align.sh
uv run python 02_g2p_align_subword.py

# Submit a GPU for extraction of all features.
bash 12_extract_features.sh

# After extraction finishes, generate subword correlations.
bash 21_correlation_subword.sh
```

Step 21 uses the **maximum frame distance within each subword** by default. Other aggregation options are the mean within the subword or the frame distance nearest its temporal midpoint:

```bash
bash 21_correlation_subword.sh --stat mean
bash 21_correlation_subword.sh --stat midpoint
```
