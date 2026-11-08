# Copyright (c) 2023 Amphion.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

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

    def extract_embedding_voxlect(self, path):
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

    def extract_embedding_voxlect_utterance(self, path):
        waveform = self._load_audio(path)
        with torch.no_grad():
            _, embedding = self.model(waveform[:, :VOXLECT_MAX_AUDIO_LENGTH], return_feature=True)
        return embedding.detach().cpu().numpy().reshape(1, -1)

    def extract_embeddings(self, path):
        if self.model_name == "voxlect":
            return self.extract_embedding_voxlect(path)
        with torch.no_grad():
            return self.model.encode_batch(self._load_audio(path), frame_level=True).squeeze(0).cpu().numpy()

    def extract_utterance_embedding(self, path):
        if self.model_name == "voxlect":
            return self.extract_embedding_voxlect_utterance(path)
        with torch.no_grad():
            return self.model.encode_batch(self._load_audio(path)).cpu().numpy().reshape(1, -1)

    def compute_utterance_similarity(self, path_ref, path_deg, return_embeddings=False):
        reference = self.extract_utterance_embedding(path_ref)
        candidate = self.extract_utterance_embedding(path_deg)
        distance = cosine_distance(reference[0], candidate[0])
        if return_embeddings:
            return distance, reference, candidate
        return distance

    def compute_similarity(self, path_ref, path_deg, return_embeddings=False):
        reference = self.extract_embeddings(path_ref)
        candidate = self.extract_embeddings(path_deg)
        result = dtw_frame_distances(reference, candidate)
        if return_embeddings:
            return (*result, reference, candidate)
        return result
