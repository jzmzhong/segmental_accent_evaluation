"""WavLM and ECAPA frame features, native utterance embeddings, and comparisons."""

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
    """Extract WavLM/ECAPA frame features and native utterance speaker embeddings."""

    def __init__(self, model_name="wavlm", device=None, savedir=None, utterance_only=False):
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.model_name = model_name
        self.utterance_only = utterance_only
        self.savedir = Path(savedir) if savedir else Path(__file__).resolve().parents[1] / "data_temp" / "models"
        self.savedir.mkdir(parents=True, exist_ok=True)
        configure_caches(self.savedir)
        self.model, self.feature_extractor = self._load_model()

    def _load_model(self):
        if self.model_name == "wavlm":
            try:
                from transformers import AutoFeatureExtractor, AutoModel, WavLMForXVector
            except ImportError as error:
                raise ImportError(
                    "WavLM extraction requires transformers. Install it with `pip install transformers`."
                ) from error
            model_class = WavLMForXVector if self.utterance_only else AutoModel
            model = model_class.from_pretrained(WAVLM_MODEL, cache_dir=str(self.savedir / "huggingface" / "hub")).to(self.device).eval()
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

    def _require_model(self, model_name, frame=False):
        if self.model_name != model_name:
            raise ValueError(f"This extractor requires {model_name}, but {self.model_name} is loaded.")
        if frame and self.utterance_only:
            raise ValueError("This instance was loaded for utterance embeddings only.")

    def extract_wavlm_frame(self, path):
        """Return WavLM backbone features shaped (frames, hidden_size)."""
        self._require_model("wavlm", frame=True)
        waveform = _load_audio(path, self.device)
        inputs = self.feature_extractor(
            waveform.cpu().numpy(), sampling_rate=SAMPLE_RATE, return_tensors="pt"
        )
        with torch.no_grad():
            outputs = self.model(inputs.input_values.to(self.device))
        return outputs.last_hidden_state.squeeze(0).cpu().numpy()

    def extract_ecapa_frame(self, path):
        """Return ECAPA pre-pooling MFA features shaped (frames, channels)."""
        self._require_model("ecapa", frame=True)
        waveform = _load_audio(path, self.device)
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

    def extract_wavlm_utterance(self, path):
        """Return the native WavLM X-vector embedding shaped (1, dimensions)."""
        self._require_model("wavlm", frame=False)
        waveform = _load_audio(path, self.device)
        if self.utterance_only:
            xvector_model = self.model
        elif not hasattr(self, "_xvector_model"):
            from transformers import WavLMForXVector
            self._xvector_model = WavLMForXVector.from_pretrained(WAVLM_MODEL, cache_dir=str(self.savedir / "huggingface" / "hub")).to(self.device).eval()
        if not self.utterance_only:
            xvector_model = self._xvector_model
        inputs = self.feature_extractor(
            waveform.cpu().numpy(), sampling_rate=SAMPLE_RATE, return_tensors="pt"
        )
        with torch.no_grad():
            outputs = xvector_model(**{key: value.to(self.device) for key, value in inputs.items()})
        return outputs.embeddings.cpu().numpy().reshape(1, -1)

    def extract_ecapa_utterance(self, path):
        """Return the native pooled ECAPA speaker embedding shaped (1, dimensions)."""
        self._require_model("ecapa", frame=False)
        waveform = _load_audio(path, self.device)
        with torch.no_grad():
            embedding = self.model.encode_batch(waveform.unsqueeze(0)).cpu().numpy()
        return embedding.reshape(1, -1)

    def compute_utterance_similarity(self, path_ref, path_deg, return_embeddings=False):
        reference_embedding = getattr(self, f"extract_{self.model_name}_utterance")(path_ref)
        candidate_embedding = getattr(self, f"extract_{self.model_name}_utterance")(path_deg)
        distance = cosine_distance(reference_embedding[0], candidate_embedding[0])
        if return_embeddings:
            return distance, reference_embedding, candidate_embedding
        return distance

    def compute_similarity(self, path_ref, path_deg, return_embeddings=False):
        reference_embeddings = getattr(self, f"extract_{self.model_name}_frame")(path_ref)
        candidate_embeddings = getattr(self, f"extract_{self.model_name}_frame")(path_deg)
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

