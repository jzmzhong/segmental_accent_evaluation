"""Frame-level speaker embedding extraction and cosine-DTW comparison."""

from pathlib import Path

import torch
import torchaudio

from distances import cosine_distance, dtw_frame_distances
from model_setup import configure_caches


WAVLM_MODEL = "microsoft/wavlm-base-sv"
ECAPA_MODEL = "speechbrain/spkrec-ecapa-voxceleb"
SAMPLE_RATE = 16000


def _load_audio(path, device):
    waveform, sample_rate = torchaudio.load(str(path))
    if sample_rate != SAMPLE_RATE:
        waveform = torchaudio.functional.resample(waveform, sample_rate, SAMPLE_RATE)
    return waveform.mean(dim=0).to(device)


class SpeakerSimilarity:
    """Extract frame-level speaker features from WavLM-SV or ECAPA-VOXCELEB."""

    def __init__(self, model_name="wavlm", device=None, savedir=None):
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.model_name = model_name
        self.savedir = Path(savedir) if savedir else Path(__file__).resolve().parents[1] / "data_temp" / "models"
        self.savedir.mkdir(parents=True, exist_ok=True)
        configure_caches(self.savedir)
        self.model, self.feature_extractor = self._load_model()

    def _load_model(self):
        if self.model_name == "wavlm":
            try:
                from transformers import AutoFeatureExtractor, AutoModel
            except ImportError as error:
                raise ImportError(
                    "WavLM extraction requires transformers. Install it with `pip install transformers`."
                ) from error
            model = AutoModel.from_pretrained(WAVLM_MODEL, cache_dir=str(self.savedir / "huggingface" / "hub")).to(self.device).eval()
            return model, AutoFeatureExtractor.from_pretrained(WAVLM_MODEL, cache_dir=str(self.savedir / "huggingface" / "hub"))

        if self.model_name == "ecapa":
            try:
                try:
                    from speechbrain.inference.speaker import EncoderClassifier
                except ImportError:
                    from speechbrain.pretrained import EncoderClassifier
            except ImportError as error:
                raise ImportError(
                    "ECAPA extraction requires speechbrain. Install it with `pip install speechbrain`."
                ) from error
            savedir = str(self.savedir / "spkrec-ecapa-voxceleb")
            model = EncoderClassifier.from_hparams(
                source=ECAPA_MODEL,
                savedir=savedir,
                run_opts={"device": str(self.device)},
            )
            model.eval()
            return model, None

        raise ValueError("model_name must be either 'wavlm' or 'ecapa'.")

    def extract_embeddings(self, path):
        waveform = _load_audio(path, self.device)
        if self.model_name == "wavlm":
            inputs = self.feature_extractor(
                waveform.cpu().numpy(), sampling_rate=SAMPLE_RATE, return_tensors="pt"
            )
            with torch.no_grad():
                outputs = self.model(inputs.input_values.to(self.device))
            return outputs.last_hidden_state.squeeze(0).cpu().numpy()

        frame_features = {}

        def capture_mfa_features(_, __, output):
            frame_features["value"] = output.detach()

        try:
            hook = self.model.mods.embedding_model.mfa.register_forward_hook(capture_mfa_features)
        except AttributeError as error:
            raise RuntimeError("The loaded ECAPA model does not expose its temporal MFA layer.") from error
        try:
            with torch.no_grad():
                self.model.encode_batch(waveform.unsqueeze(0))
        finally:
            hook.remove()
        if "value" not in frame_features:
            raise RuntimeError("ECAPA did not emit temporal speaker features.")
        return frame_features["value"].squeeze(0).transpose(0, 1).cpu().numpy()

    def extract_utterance_embedding(self, path):
        """Return the model's native pooled utterance-level embedding, shaped (1, dim)."""
        waveform = _load_audio(path, self.device)
        if self.model_name == "wavlm":
            if not hasattr(self, "_xvector_model"):
                from transformers import WavLMForXVector
                self._xvector_model = WavLMForXVector.from_pretrained(WAVLM_MODEL, cache_dir=str(self.savedir / "huggingface" / "hub")).to(self.device).eval()
            inputs = self.feature_extractor(
                waveform.cpu().numpy(), sampling_rate=SAMPLE_RATE, return_tensors="pt"
            )
            with torch.no_grad():
                outputs = self._xvector_model(inputs.input_values.to(self.device))
            return outputs.embeddings.cpu().numpy().reshape(1, -1)

        with torch.no_grad():
            embedding = self.model.encode_batch(waveform.unsqueeze(0)).cpu().numpy()
        return embedding.reshape(1, -1)

    def compute_utterance_similarity(self, path_ref, path_deg, return_embeddings=False):
        reference_embedding = self.extract_utterance_embedding(path_ref)
        candidate_embedding = self.extract_utterance_embedding(path_deg)
        distance = cosine_distance(reference_embedding[0], candidate_embedding[0])
        if return_embeddings:
            return distance, reference_embedding, candidate_embedding
        return distance

    def compute_similarity(self, path_ref, path_deg, return_embeddings=False):
        reference_embeddings = self.extract_embeddings(path_ref)
        candidate_embeddings = self.extract_embeddings(path_deg)
        distance, reference_values, candidate_values = dtw_frame_distances(
            reference_embeddings, candidate_embeddings
        )
        if return_embeddings:
            return (
                distance,
                reference_values,
                candidate_values,
                reference_embeddings,
                candidate_embeddings,
            )
        return distance, reference_values, candidate_values

