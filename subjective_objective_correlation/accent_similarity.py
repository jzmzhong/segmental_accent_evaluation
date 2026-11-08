"""Frame and utterance accent embeddings from GenAID and VoxLect."""

import os
from pathlib import Path
import sys

import numpy as np
import torch
import torchaudio

from distances import cosine_distance, dtw_frame_distances
from model_setup import configure_caches

SAMPLE_RATE = 16000
VOXLECT_MAX_AUDIO_LENGTH = 15 * SAMPLE_RATE
DEFAULT_GENAID_SOURCE = "jzmzhong/accent-id-genaid"


class AccentSimilarity:
    def __init__(self, model_name, device=None, cache_dir=None, genaid_source=None, voxlect_repo=None):
        self.model_name = model_name
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.cache_dir = Path(cache_dir) if cache_dir else Path(__file__).resolve().parents[1] / "data_temp/models"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        configure_caches(self.cache_dir)

        if model_name == "genaid":
            try:
                from speechbrain.inference.interfaces import foreign_class
            except ImportError:
                from speechbrain.pretrained.interfaces import foreign_class

            from model_setup import download_genaid

            source = download_genaid(
                genaid_source or os.environ.get("GENAID_SOURCE", DEFAULT_GENAID_SOURCE),
                self.cache_dir,
            )
            self.model = foreign_class(
                source=str(source),
                pymodule_file=str(source / "custom_interface.py"),
                savedir=str(self.cache_dir / "genaid"),
                overrides={
                    "pretrained_path": str(source),
                    "wav2vec2": {"save_path": str(self.cache_dir / "huggingface" / "hub")},
                },
                classname="CustomEncoderWav2vec2Classifier",
                run_opts={"device": str(self.device)},
            )
        elif model_name == "voxlect":
            repo = voxlect_repo or os.environ.get("VOXLECT_REPO") or self.cache_dir / "voxlect-source"
            if repo:
                sys.path.insert(0, str(Path(repo).expanduser().resolve()))
            try:
                from src.model.dialect.whisper_dialect import WhisperWrapper
            except ImportError as error:
                raise ImportError("VoxLect requires its source repository; set --voxlect-repo or VOXLECT_REPO.") from error
            self.model = WhisperWrapper.from_pretrained(
                "tiantiaf/voxlect-english-dialect-whisper-large-v3",
                cache_dir=str(self.cache_dir / "huggingface" / "hub"),
            ).to(self.device)
        else:
            raise ValueError("model_name must be 'genaid' or 'voxlect'.")
        self.model.eval()

    def _load_audio(self, path):
        waveform, sample_rate = torchaudio.load(str(path))
        if sample_rate != SAMPLE_RATE:
            waveform = torchaudio.functional.resample(waveform, sample_rate, SAMPLE_RATE)
        return waveform.mean(dim=0, keepdim=True).float().to(self.device)

    def extract_voxlect_frame(self, path):
        """Return valid VoxLect temporal features shaped (frames, dimensions)."""
        self._require_model("voxlect")
        waveform = self._load_audio(path)
        frame_embeddings = {}

        def capture_frames(module, inputs, output):
            # model_seq output is [batch, hidden_dim, frames].
            frame_embeddings["value"] = output.transpose(1, 2).detach().cpu()

        hook = self.model.model_seq.register_forward_hook(capture_frames)
        try:
            with torch.no_grad():
                length = torch.tensor([waveform.shape[1]], device=self.device)
                self.model(waveform, length=length)
        finally:
            hook.remove()
        frame_count = self.model._get_feat_extract_output_lengths(length).item()
        return frame_embeddings["value"][0][:frame_count].numpy()

    def extract_voxlect_utterance(self, path):
        """Return the native pooled Voxlect embedding, using at most 15 seconds."""
        self._require_model("voxlect")
        waveform = self._load_audio(path)
        with torch.no_grad():
            _, embedding = self.model(waveform[:, :VOXLECT_MAX_AUDIO_LENGTH], return_feature=True)
        return embedding.detach().cpu().numpy().reshape(1, -1)

    def _require_model(self, model_name):
        if self.model_name != model_name:
            raise ValueError(f"This extractor requires {model_name}, but {self.model_name} is loaded.")

    def extract_genaid_frame(self, path):
        """Return GenAID's XLSR frame features shaped (frames, dimensions)."""
        self._require_model("genaid")
        with torch.no_grad():
            return self.model.encode_batch(self._load_audio(path), frame_level=True).squeeze(0).cpu().numpy()

    def extract_genaid_utterance(self, path):
        """Return GenAID's native pooled/MLP embedding shaped (1, 64)."""
        self._require_model("genaid")
        with torch.no_grad():
            return self.model.encode_batch(self._load_audio(path)).cpu().numpy().reshape(1, -1)

    def compute_utterance_similarity(self, path_ref, path_deg, return_embeddings=False):
        reference = getattr(self, f"extract_{self.model_name}_utterance")(path_ref)
        candidate = getattr(self, f"extract_{self.model_name}_utterance")(path_deg)
        distance = cosine_distance(reference[0], candidate[0])
        if return_embeddings:
            return distance, reference, candidate
        return distance

    def compute_similarity(self, path_ref, path_deg, return_embeddings=False):
        reference = getattr(self, f"extract_{self.model_name}_frame")(path_ref)
        candidate = getattr(self, f"extract_{self.model_name}_frame")(path_deg)
        result = dtw_frame_distances(reference, candidate)
        if return_embeddings:
            return (*result, reference, candidate)
        return result


class GenAIDPooling:
    """Load only GenAID's trained pooling/head to reuse cached XLSR frames."""

    def __init__(self, device=None, cache_dir=None, source=None):
        from hyperpyyaml import load_hyperpyyaml
        from model_setup import download_genaid

        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        cache_dir = Path(cache_dir) if cache_dir else Path(__file__).resolve().parents[1] / "data_temp/models"
        configure_caches(cache_dir)
        source = download_genaid(source or os.environ.get("GENAID_SOURCE", DEFAULT_GENAID_SOURCE), cache_dir)
        with (source / "hyperparams.yaml").open() as handle:
            # Replace the encoder before constructing YAML objects. The pretrainer
            # is not invoked: only model.ckpt (the two MLPs) is needed here.
            hparams = load_hyperpyyaml(handle, overrides={"wav2vec2": None, "pretrained_path": str(source)})
        state = torch.load(source / "model.ckpt", map_location="cpu", weights_only=True)
        # Training checkpoints may also contain output classifiers/loss heads.
        # Only ModuleList item 0 (the pre-output embedding MLP) is required.
        hparams["preout_mlp"].load_state_dict(
            {key.removeprefix("0."): value for key, value in state.items() if key.startswith("0.")}
        )
        self.pool = hparams["avg_pool"].to(self.device).eval()
        self.head = hparams["preout_mlp"].to(self.device).eval()

    def extract_genaid_utterance_from_frames(self, frames):
        """Apply native GenAID pooling/MLP to XLSR frames; return (1, 64)."""
        frames = torch.as_tensor(frames, dtype=torch.float32, device=self.device)
        with torch.inference_mode():
            pooled = self.pool(frames.unsqueeze(0)).reshape(1, -1)
            return self.head(pooled).cpu().numpy().reshape(1, -1)

    def __call__(self, frames):
        return self.extract_genaid_utterance_from_frames(frames)
