"""Frame-level F0 and formant extraction (Praat pitch + Burg formants) with DTW comparison."""

import numpy as np
from distances import aggregate_frame_distances, dtw_alignment, rmse_distance
from scipy.interpolate import pchip_interpolate


def extract_f0_formants(
    path,
    sample_rate=16000,
    hop_length=160,
    fmin=75,
    fmax=500,
    n_formants=3,
    max_formant_hz=5500.0,
    interpolate=False,
):
    """Return one $F_0, F_1, ..., F_n$ feature vector for each audio frame.

    F0 is tracked with Praat's autocorrelation pitch method in very-accurate mode, with
    floor/ceiling (75/500 Hz by default) covering both male and female speech. Formants
    are tracked with Praat's Burg method at Praat's default analysis settings (via
    parselmouth). When `interpolate` is True, F0 and each formant column are filled
    across their own invalid (zero) frames via pchip in the same pass; otherwise
    invalid frames are left as zero for every column.
    """
    import parselmouth

    sound = parselmouth.Sound(str(path))
    if round(sound.sampling_frequency) != sample_rate:
        sound = sound.resample(sample_rate)

    time_step = hop_length / sample_rate
    pitch = sound.to_pitch_ac(
        time_step=time_step, pitch_floor=fmin, pitch_ceiling=fmax, very_accurate=True
    )
    # time_step=None lets Praat use its own default Burg analysis grid (25% of the default window).
    formant = sound.to_formant_burg(time_step=None, maximum_formant=max_formant_hz)

    # Frame centers at time_step/2, 3*time_step/2, ... covering the full duration, including the trailing partial window.
    frame_count = max(int(np.ceil(sound.duration / time_step)), 1)
    frame_times = time_step / 2 + np.arange(frame_count) * time_step

    features = np.zeros((frame_count, n_formants + 1), dtype=np.float32)
    for index, frame_time in enumerate(frame_times):
        f0 = pitch.get_value_at_time(frame_time)
        is_voiced = f0 is not None and not np.isnan(f0) and f0 != 0.0
        if not is_voiced:
            continue
        features[index, 0] = f0
        for formant_index in range(1, n_formants + 1):
            value = formant.get_value_at_time(formant_index, frame_time)
            features[index, formant_index] = 0.0 if value is None or np.isnan(value) else value

    if interpolate:
        for column in range(features.shape[1]):
            valid_indices = np.flatnonzero(features[:, column] != 0)
            if len(valid_indices) == 1:
                features[:, column] = features[valid_indices[0], column]
            elif len(valid_indices) > 1:
                features[:, column] = pchip_interpolate(
                    valid_indices, features[valid_indices, column], np.arange(frame_count)
                )
    return features


def _dtw_frame_distances(reference_features, candidate_features):
    """Align frames on the full feature vector, then score F0 and formants separately."""

    _, _, path = dtw_alignment(reference_features, candidate_features, metric="rmse")
    reference_indices = np.asarray(path[0])
    candidate_indices = np.asarray(path[1])

    def _aggregate(local_costs):
        reference_values, candidate_values = aggregate_frame_distances(
            path, local_costs, len(reference_features), len(candidate_features)
        )
        return float(local_costs.mean()), reference_values, candidate_values

    f0_costs = np.abs(
        reference_features[reference_indices, 0] - candidate_features[candidate_indices, 0]
    )
    formant_costs = np.array([
        rmse_distance(reference_features[reference_index, 1:], candidate_features[candidate_index, 1:])
        for reference_index, candidate_index in zip(reference_indices, candidate_indices)
    ])

    return _aggregate(f0_costs), _aggregate(formant_costs)


def compute_similarity(path_ref, path_deg, return_embeddings=False, **kwargs):
    """Compare F0 and formant sequences, returning a (distance, reference_values, candidate_values)
    result for F0 and another for the formants."""
    reference_features = extract_f0_formants(path_ref, **kwargs)
    candidate_features = extract_f0_formants(path_deg, **kwargs)
    f0_result, formant_result = _dtw_frame_distances(reference_features, candidate_features)
    if return_embeddings:
        return f0_result, formant_result, reference_features, candidate_features
    return f0_result, formant_result
