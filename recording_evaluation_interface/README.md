# Recording and Evaluation Interface

This directory contains two interfaces for speech recording and evaluation. In Stage 1, participants record themselves reading a set of selected utterances and provide demographic information. In Stage 2, some of these recordings are used to generate synthetic speech in the participants' voices. Participants then evaluate their own generated speech (own-voice evaluation), or other listeners from the same accent region evaluate it (stranger-voice evaluation).

## Stage 1 Voice Recording

### Preparation

- Recording utterances: [`utterances.json`](stage_1_prolific_recording/data/utterances.json)
- Recording and survey responses upload handler: [`save-recording.cgi`](stage_1_prolific_recording/save-recording.cgi)
- Survey trials: [`experiment.js`](stage_1_prolific_recording/js/experiment.js)

Before deployment, update the utterance list, the directory used to save recordings and survey responses, and the Prolific completion code.

### Running locally

```bash
python3 -m http.server 8000 --directory stage_1_prolific_recording
```

The recording interface will be available at [localhost:8000](http://localhost:8000/?PROLIFIC_PID=testparticipant&STUDY_ID=teststudy&SESSION_ID=testsession) with the example Prolific parameters. To preview the recording procedure with two utterances, add `debug=1` to the URL. A deployed example is available [here](https://sweb.inf.ed.ac.uk/~s2526235/listening_tests/202607_accent_evaluation/stage_1_prolific_recording/?PROLIFIC_PID=testparticipant&STUDY_ID=teststudy&SESSION_ID=testsession).

### Collected data

Participant recordings and metadata will be stored together in a private participant directory:

```text
<DATA_ROOT>/<PARTICIPANT_ID>/
├── recording_<PARTICIPANT_ID>_<TIMESTAMP>.json
├── <PARTICIPANT_ID>_<UTTERANCE_ID>.webm
└── ...
```

## Stage 2 Accent Evaluation

### Preparation

- Segmented utterances: [`utterances_segmented.json`](stage_2_accent_evaluation/data/utterances_segmented.json)
- Survey configuration and instructions: [`content.json`](stage_2_accent_evaluation/data/content.json)
- Survey responses upload handler: [`save-responses.cgi`](stage_2_accent_evaluation/save-responses.cgi)
- Audio directory: [`wav/`](stage_2_accent_evaluation/data/wav/)

Before deployment, update the segmented utterances, listening-test instructions, the directory used to save survey responses, and the Prolific completion code.

Place the audio files to be evaluated in the following directory, using the specified filename formats:

```text
# Reference recordings
stage_2_accent_evaluation/data/wav/<SPEAKER_ID>/<SPEAKER_ID>_<UTTERANCE_ID>.wav
# Generated speech
stage_2_accent_evaluation/data/wav/<SPEAKER_ID>/cloned_<SPEAKER_ID>_<UTTERANCE_ID>_ref_<REFERENCE_UTTERANCE_ID>_<TTS_SYSTEM>.wav
```

### Running locally

```bash
python3 -m http.server 8000 --directory stage_2_accent_evaluation
```

The evaluation interface will be available at [localhost:8000](http://localhost:8000/?PROLIFIC_PID=testparticipant&STUDY_ID=teststudy&SESSION_ID=testsession) with the example Prolific parameters. It supports two modes: own-voice evaluation and stranger-voice evaluation.

For own-voice evaluation, `PROLIFIC_PID` must identify a participant on the pre-approved list who contributed a recording. For stranger-voice evaluation, add the `TAR_SPK=<speaker_id>` URL parameter to specify whose voice to evaluate.

To preview a randomly selected evaluation page, add `preview=question` to the URL. A deployed example is available [here](https://sweb.inf.ed.ac.uk/~s2526235/listening_tests/202607_accent_evaluation/stage_2_accent_evaluation/?PROLIFIC_PID=testparticipant&STUDY_ID=teststudy&SESSION_ID=testsession&TAR_SPK=69e8b0adf78ba4d3ede8b1f5).
