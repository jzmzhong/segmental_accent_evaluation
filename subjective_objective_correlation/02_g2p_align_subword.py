import json
import os
import glob
import re
from tqdm import tqdm
# load tg reader
from praatio import textgrid
## add the script directory to the import path for the local g2p_aligner
import sys
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
## load g2p_aligner
from g2p_aligner.Aligner import Aligner
from g2p_aligner.pl_table import pl_table
g2p_aligner = Aligner(pl_table)

def extract_word_phone_mapping(tg):
    words = tg.getTier("words").entries
    phones = tg.getTier("phones").entries
    return words, phones

def get_words_with_phones(tg_path, word_tier_name="words", phone_tier_name="phones"):
    tg = textgrid.openTextgrid(tg_path, includeEmptyIntervals=False)
    word_tier = tg.getTier(word_tier_name)
    phone_tier = tg.getTier(phone_tier_name)
    results = []
    for w_start, w_end, w_label in word_tier.entries:
        p_info = [
            (p_start, p_end, p_label.lower())
            for p_start, p_end, p_label in phone_tier.entries
            if p_start >= w_start and p_end <= w_end
        ]
        p_label = [p[2] for p in p_info]
        results.append((w_start, w_end, w_label.replace("'", ""), p_label, p_info)) # replace apostrophes in words to avoid issues with g2p alignment
    return results

def align_letters_with_phones(results):
    for w_idx, (w_start, w_end, word, phones, p_info) in enumerate(results):

        # remove secondary stress markers from phones
        phones = [p.strip("2") for p in phones]

        alignment = g2p_aligner.doAlignment(phones, word)
        alignment = [[a[1], a[0]] for a in alignment] # swap to g -> p order
        g_idx, p_idx = 0, 0
        g_info = [] # list of tuples (l_start, l_end, letter) for each letter in the word
        # print("Alignment for word '%s': %s, phones: %s" % (word, alignment, phones))
        for a in alignment:
            if a[0] == "_epsilon_":
                print("Warning: No letter aligned for phone '%s' in word '%s'." % (a[1], word))
                p_idx += 1
            elif a[1] == "_epsilon_":
                # print("Warning: No phone aligned for letter '%s' in word '%s'." % (a[0], word))
                g_info.append((-1, -1, a[0])) # no phone aligned, set start and end to -1
                g_idx += 1
            else:
                aligned_phones = a[1].split("-")
                num_phones = len(aligned_phones)
                assert p_idx+num_phones-1 < len(phones), "Error: More phones aligned than available for word: '%s', phones: '%s'" % (word, phones)
                assert phones[p_idx:p_idx+num_phones] == aligned_phones, "Error: Aligned phones '%s' do not match expected phones '%s' for word '%s'." % (aligned_phones, phones[p_idx:p_idx+num_phones], word)
                l_start, l_end = p_info[p_idx][0], p_info[p_idx+num_phones-1][1] # start of first phone, end of last phone
                g_info.append((l_start, l_end, a[0]))
                g_idx += 1
                p_idx += num_phones
                assert g_idx <= len(word), "Error: More letters aligned than available in word: '%s', phones: '%s'." % (word, phones)
        assert len(g_info) == len(word), "Error: Number of aligned letters '%s' does not match length of word: '%s', phones: '%s'." % (str(g_info), word, phones)
        results[w_idx] = (w_start, w_end, word, phones, p_info, g_info)
    return results


def normalise_text(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def get_utterance_id(filename, utterance_ids):
    stem = os.path.splitext(filename)[0]
    stem_parts = stem.split("_")
    for index in range(len(stem_parts) - 1):
        utterance_id = "_".join(stem_parts[index:index + 2])
        if utterance_id in utterance_ids:
            return utterance_id
    raise ValueError(f"Could not identify an utterance ID in {filename}.")

def group_subwords(segmented_text):
    """Group pipe-delimited subwords into their corresponding spoken words."""
    groups = []
    current_group = []
    for segment in segmented_text.split("|"):
        if normalise_text(segment):
            current_group.append(segment)
        if any(character.isspace() for character in segment):
            if current_group:
                groups.append(current_group)
                current_group = []
    if current_group:
        groups.append(current_group)
    return groups


def get_subword_timings(word_results, segmented_text):
    subword_groups = group_subwords(segmented_text)
    # print(f"Segmented text: {segmented_text}")
    # print(f"Subword groups: {subword_groups}")
    # print(f"Word results: {[word for (_, _, word, _, _, _) in word_results]}")
    if len(subword_groups) != len(word_results):
        raise ValueError(
            f"Segmented text contains {len(subword_groups)} words but TextGrid contains "
            f"{len(word_results)} words."
        )

    timings = []
    for (word_start, word_end, word, _, p_info, g_info), subwords in zip(word_results, subword_groups):
        expected_word = "".join(normalise_text(subword) for subword in subwords)
        if normalise_text(word) != expected_word:
            raise ValueError(
                f"Text mismatch: TextGrid word '{word}' does not match segmented "
                f"subwords '{'|'.join(subwords)}'."
            )

        word_has_no_timed_letters = p_info and all(letter[0] < 0 for letter in g_info)
        letter_index = 0
        for subword in subwords:
            letter_count = len(normalise_text(subword))
            aligned_letters = g_info[letter_index:letter_index + letter_count]
            letter_index += letter_count
            timed_letters = [letter for letter in aligned_letters if letter[0] >= 0]
            if timed_letters:
                start_time = timed_letters[0][0]
                end_time = timed_letters[-1][1]
                phones = [
                    phone for phone in p_info
                    if phone[0] < end_time and phone[1] > start_time
                ]
            elif word_has_no_timed_letters:
                start_time, end_time, phones = word_start, word_end, p_info
            else:
                import pdb; pdb.set_trace()
                start_time, end_time, phones = -1, -1, []
            timings.append((start_time, end_time, subword, phones))

        if letter_index != len(g_info):
            raise ValueError(f"Subwords did not consume every letter in '{word}'.")
    return timings

if __name__ == "__main__":

    # input and output directories
    DATA_DIR = SCRIPT_DIR.parent / "data_temp"
    IN_DIR = DATA_DIR / "wav_txt_pairs_mfa"
    OUT_DIR = DATA_DIR / "wav_txt_pairs_g2psubword"
    SEGMENTED_TEXT_PATH = SCRIPT_DIR.parent / "data" / "utterances_segmented.json"
    os.makedirs(OUT_DIR, exist_ok=True)

    with open(SEGMENTED_TEXT_PATH, "r") as f:
        utterances = {
            entry["id"]: entry["text"]
            for entry in json.load(f)
        }

    # process each TextGrid file
    # for tg_path in tqdm(glob.glob(os.path.join(IN_DIR, "**/*.TextGrid"), recursive=True)):
    for tg_path in glob.glob(os.path.join(IN_DIR, "**/*.TextGrid"), recursive=True):
        if tg_path.endswith(".TextGrid"):
            # print(f"Processing {tg_path}...")

            relative_path = os.path.relpath(tg_path, IN_DIR)

            try:
                results = align_letters_with_phones(get_words_with_phones(tg_path))
            except Exception as e:
                print(f"Error processing {tg_path}: {e}")
                continue
            utterance_id = get_utterance_id(tg_path, utterances)
            # print("Processing utterance ID:", utterance_id, "from file:", tg_path)
            subword_timings = get_subword_timings(results, utterances[utterance_id])
            out_path = os.path.join(OUT_DIR, relative_path.replace(".TextGrid", "_aligned.txt"))
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w") as f:
                for start_time, end_time, subword, phones in subword_timings:
                    phone_labels = " ".join(phone[2] for phone in phones)
                    phone_info = " ".join(
                        f"{phone[0]:.3f},{phone[1]:.3f},{phone[2]}"
                        for phone in phones
                    )
                    f.write(
                        f"{start_time:.3f}\t{end_time:.3f}\t{subword}\t"
                        f"{phone_labels}\t{phone_info}\n"
                    )
    
