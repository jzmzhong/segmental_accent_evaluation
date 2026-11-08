#!/bin/bash
set -e

# load the conda environment for MFA
source $HOME/miniconda3/bin/activate mfa

mfa model download acoustic english_us_arpa
mfa model download dictionary english_us_arpa

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RAW_DATA_DIR="${SCRIPT_DIR}/../data"
DATA_TEMP_DIR="${SCRIPT_DIR}/../data_temp"

# find wav and txt pairs in the raw data directory and reorganize them into the temporary data directory with wav-txt pairs for each speaker
python "${SCRIPT_DIR}/reorganise.py" "$RAW_DATA_DIR" "$DATA_TEMP_DIR"

IN_DIR=${DATA_TEMP_DIR}/wav_txt_pairs
OUT_DIR=${IN_DIR}_mfa
mkdir -p "${OUT_DIR}"

mfa align --clean "${IN_DIR}" english_us_arpa english_us_arpa "${OUT_DIR}"
