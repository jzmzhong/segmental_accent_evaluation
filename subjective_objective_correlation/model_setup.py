"""Download feature-extraction models without instantiating neural networks."""

import argparse
import os
from pathlib import Path
import subprocess

DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[1] / "data_temp" / "models"
GENAID_MODEL = "jzmzhong/accent-id-genaid"
VOXLECT_REPOSITORY = "https://github.com/tiantiaf0627/voxlect.git"
MODEL_REPOSITORIES = {
    "genaid": (GENAID_MODEL, "facebook/wav2vec2-large-xlsr-53"),
    "voxlect": ("tiantiaf/voxlect-english-dialect-whisper-large-v3",
                "openai/whisper-large-v3", "openai/whisper-tiny"),
    "wavlm": ("microsoft/wavlm-base-sv",),
    "ecapatdnn": ("speechbrain/spkrec-ecapa-voxceleb",),
}
MODEL_CHOICES = ("ppg", "genaid", "voxlect", "wavlm", "ecapatdnn", "f0_formants")


def configure_caches(model_dir):
    model_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(model_dir / "huggingface")
    os.environ["HF_HUB_CACHE"] = str(model_dir / "huggingface" / "hub")
    os.environ["TORCH_HOME"] = str(model_dir / "torch")
    os.environ["XDG_CACHE_HOME"] = str(model_dir / "xdg")
    os.environ["MPLCONFIGDIR"] = str(model_dir / "matplotlib")
    os.environ["NUMBA_CACHE_DIR"] = str(model_dir / "numba")


def download_snapshot(repo_id, model_dir):
    """Cache model assets, preferring safetensors over duplicate PyTorch weights."""
    from huggingface_hub import list_repo_files, snapshot_download

    files = list_repo_files(repo_id)
    patterns = ["*.json", "*.txt", "*.yaml", "*.yml", "*.py", "*.ckpt", "*.model"]
    patterns.append("*.safetensors" if any(f.endswith(".safetensors") for f in files) else "*.bin")
    return Path(snapshot_download(
        repo_id, cache_dir=str(model_dir / "huggingface" / "hub"),
        allow_patterns=patterns,
    ))


def download_genaid(source=GENAID_MODEL, model_dir=DEFAULT_MODEL_DIR):
    source_path = Path(source).expanduser()
    if source_path.is_dir():
        directory = source_path.resolve()
    else:
        from huggingface_hub import snapshot_download
        from huggingface_hub.errors import LocalEntryNotFoundError

        try:
            directory = Path(snapshot_download(
                str(source), cache_dir=str(Path(model_dir) / "huggingface" / "hub"),
                local_files_only=True,
            ))
            required = ("custom_interface.py", "hyperparams.yaml", "model.ckpt",
                        "wav2vec2.ckpt", "accent_encoder.txt")
            if not all((directory / name).is_file() for name in required):
                directory = download_snapshot(str(source), Path(model_dir))
        except LocalEntryNotFoundError:
            directory = download_snapshot(str(source), Path(model_dir))
    for filename in ("custom_interface.py", "hyperparams.yaml", "model.ckpt",
                     "wav2vec2.ckpt", "accent_encoder.txt"):
        if not (directory / filename).is_file():
            raise FileNotFoundError(f"GenAID asset missing: {directory / filename}")
    return directory


def download_models(model_dir=DEFAULT_MODEL_DIR, models=MODEL_CHOICES):
    model_dir = Path(model_dir).expanduser().resolve()
    configure_caches(model_dir)
    downloaded = set()
    for name in models:
        if name == "f0_formants":
            print("F0/formants: Praat algorithms; no model weights required.")
            continue
        if name == "ppg":
            from huggingface_hub import hf_hub_download
            hf_hub_download("CameronChurchwell/ppgs", "mel-800k.pt",
                            cache_dir=str(model_dir / "huggingface" / "hub"))
            print("Downloaded PPG mel checkpoint.")
            continue
        for repo in MODEL_REPOSITORIES[name]:
            if repo not in downloaded:
                print(f"Downloading {repo}", flush=True)
                if repo == GENAID_MODEL:
                    download_genaid(repo, model_dir)
                else:
                    download_snapshot(repo, model_dir)
                downloaded.add(repo)
        if name == "voxlect":
            source_dir = model_dir / "voxlect-source"
            if not source_dir.exists():
                subprocess.run(["git", "clone", "--depth", "1", VOXLECT_REPOSITORY,
                                str(source_dir)], check=True)
            if not (source_dir / "src/model/dialect/whisper_dialect.py").is_file():
                raise FileNotFoundError(f"Invalid VoxLect source checkout: {source_dir}")
    print(f"Models ready in {model_dir}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--models", nargs="+", choices=MODEL_CHOICES, default=MODEL_CHOICES)
    args = parser.parse_args()
    download_models(args.model_dir, args.models)


if __name__ == "__main__":
    main()
