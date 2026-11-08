"""Phonetic posteriorgram extraction and DTW comparison.

PPGs retain their native (phones, frames) layout in returned caches.
"""

import numpy as np

from distances import dtw_frame_distances


def remove_sil(ppg):
    """Trim leading and trailing silence (phone ID 39)."""
    speech = np.flatnonzero(np.argmax(ppg, axis=0) != 39)
    if not len(speech):
        raise ValueError("Cannot align a PPG containing only silence.")
    return ppg[:, speech[0]:speech[-1] + 1]


def extract_sil(ppg):
    return np.flatnonzero(np.argmax(ppg, axis=0) == 39)


def DTW_PPG(ppg_a, ppg_b, mode, remove_silence=False):
    if remove_silence:
        ppg_a, ppg_b = remove_sil(ppg_a), remove_sil(ppg_b)
    distance, reference_values, candidate_values = dtw_frame_distances(ppg_a.T, ppg_b.T, mode)
    reference_values[extract_sil(ppg_a)] = 0
    candidate_values[extract_sil(ppg_b)] = 0
    return distance, reference_values, candidate_values


def extract_ppgs(path_ref, path_deg, return_embeddings=False,
                 distance_metric="jensenshannon", remove_silence=False, gpu=None):
    import ppgs

    def extract(path):
        audio = ppgs.load.audio(str(path))
        return ppgs.from_audio(audio, ppgs.SAMPLE_RATE, gpu=gpu).squeeze(0).float().cpu().numpy()

    reference, candidate = extract(path_ref), extract(path_deg)
    # Keep returned features on the same time axes as their frame distances.
    if remove_silence:
        reference, candidate = remove_sil(reference), remove_sil(candidate)
    result = DTW_PPG(reference, candidate, distance_metric)
    if return_embeddings:
        return (*result, reference, candidate)
    return result
