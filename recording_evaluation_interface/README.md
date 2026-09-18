# Recording and Evaluation Interface

This part of the repository contains the two interfaces we use for speech data recording and evaluation. In the first stage, we set up an interface to collect recordings from participants reading pre-selected utterances, as well as some of their demographic information. In the second stage, we use some of the collected recordings to generate synthetic speech in their voice, and either ask themselves to evaluate these synthetic speech (own-voice evaluation) or ask others (from the same accent region) to evaluation their speech (stranger-voice evaluation).

## Stage 1 Voice Recording

### Preparation

- Recording utterances: [`utterances.json`](stage_1_prolific_recording/data/utterances.json)
- Recording and survey responses upload handler: [`save-recording.cgi`](stage_1_prolific_recording/save-recording.cgi)
- Survey trials: [`experiment.js`](stage_1_prolific_recording/js/experiment.js)

Before deployment, please make sure to update the recording utterances, the directory to save audio recordings and survey responses, and Prolific completion code.

### Running locally

```bash
python3 -m http.server 8000 --directory stage_1_prolific_recording
```

The recording interface will be available at [Local URL with Prolific metadata](http://localhost:8000/?PROLIFIC_PID=testparticipant&STUDY_ID=teststudy&SESSION_ID=testsession). For a quick preview of the recording procedures, add ``debug=1`` to the URL parameters for a quick 2 utterance recording. A sample deployed study can  seen at [Hosted URL with Prolific metadata](https://sweb.inf.ed.ac.uk/~s2526235/listening_tests/202607_accent_evaluation/stage_1_prolific_recording/?PROLIFIC_PID=testparticipant&STUDY_ID=teststudy&SESSION_ID=testsession)

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

Before deployment, please make sure to update the segmented utterances, listening test instructions, the directory to save survey responses, and Prolific completion code.

The audios to be evaluated should be placed in the following directory with following format.
```text
# recording as reference speech
stage_2_accent_evaluation/data/wav/<SPEAKER_ID>/<SPEAKER_ID>_<UTTERANCE_ID>.wav
# TTS generation as candidate speech
stage_2_accent_evaluation/data/wav/<SPEAKER_ID>/cloned_<SPEAKER_ID>_<UTTERANCE_ID>_ref_<REFERENCE_UTTERANCE_ID>_<TTS_SYSTEM>.wav
```

### Running locally

```bash
python3 -m http.server 8000 --directory stage_2_accent_evaluation
```

The evaluation interface will be available at [Local URL with Prolific metadata](http://localhost:8000/?PROLIFIC_PID=testparticipant&STUDY_ID=teststudy&SESSION_ID=testsession). The evaluation supports two separate modes: own-voice evaluation and stranger-voice evaluation.

For the own-voice evaluation mode, the URL only accepts PROLIFIC_PID in the pre-approved speaker lists who have contributed their recordings. For the stranger-voice evaluation, an additional URL parameter ``TAR_SPK=xxx`` needs to be provided to indicate which voice to evaluate.

For a quick preview of a random evaluation page, add ``preview=question`` to the URL parameters. A sample deployed study can bee seen at [Hosted URL with Prolific metadata](https://sweb.inf.ed.ac.uk/~s2526235/listening_tests/202607_accent_evaluation/stage_2_accent_evaluation/?PROLIFIC_PID=testparticipant&STUDY_ID=teststudy&SESSION_ID=testsession&TAR_SPK=69e8b0adf78ba4d3ede8b1f5).
