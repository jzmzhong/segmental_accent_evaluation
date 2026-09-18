(function () {
  const info = {
    name: "record-audio-trial",
    version: "0.1.0",
    parameters: {
      participant_id: {
        type: jsPsychModule.ParameterType.STRING,
        default: "unknown_participant",
      },
      utterance_id: {
        type: jsPsychModule.ParameterType.STRING,
        default: null,
      },
      utterance_text: {
        type: jsPsychModule.ParameterType.STRING,
        default: "",
      },
      trial_number: {
        type: jsPsychModule.ParameterType.INT,
        default: 1,
      },
      total_trials: {
        type: jsPsychModule.ParameterType.INT,
        default: 1,
      },
      min_duration_ms: {
        type: jsPsychModule.ParameterType.INT,
        default: 800,
      },
      max_duration_ms: {
        type: jsPsychModule.ParameterType.INT,
        default: 30000,
      },
      allow_rerecord: {
        type: jsPsychModule.ParameterType.BOOL,
        default: true,
      },
    },
    data: {
      task: {
        type: jsPsychModule.ParameterType.STRING,
      },
      utterance_id: {
        type: jsPsychModule.ParameterType.STRING,
      },
      utterance_text: {
        type: jsPsychModule.ParameterType.STRING,
      },
      audio_filename: {
        type: jsPsychModule.ParameterType.STRING,
      },
      audio_mime_type: {
        type: jsPsychModule.ParameterType.STRING,
      },
      audio_size_bytes: {
        type: jsPsychModule.ParameterType.INT,
      },
      recording_duration_ms: {
        type: jsPsychModule.ParameterType.INT,
      },
    },
  };

  class RecordAudioTrialPlugin {
    constructor(jsPsych) {
      this.jsPsych = jsPsych;
    }

    trial(displayElement, trial) {
      let mediaRecorder = null;
      let stream = null;
      let chunks = [];
      let recordingStartedAt = 0;
      let stopTimer = null;
      let currentAudio = null;
      let currentBlob = null;

      displayElement.innerHTML = `
        <main class="recording-panel">
          <div class="recording-meta">
            <span>Utterance ${trial.trial_number} of ${trial.total_trials}</span>
            <span id="timer">00:00</span>
          </div>
          <section class="utterance-card" aria-labelledby="utterance-label">
            <p class="utterance-label" id="utterance-label">Read aloud</p>
            <p class="utterance-text">${escapeHtml(trial.utterance_text)}</p>
          </section>
          <p>Record yourself reading the sentence naturally. You can listen back and re-record before continuing.</p>
          <div class="recording-controls">
            <button type="button" id="start-recording">Start recording</button>
            <button type="button" id="stop-recording" class="danger" disabled>Stop recording</button>
            <button type="button" id="rerecord" class="secondary" disabled>Record again</button>
            <button type="button" id="continue" disabled>Continue</button>
          </div>
          <div class="recording-status" id="recording-status" role="status">Ready.</div>
          <audio class="recording-playback" id="playback" controls hidden></audio>
        </main>
      `;

      const startButton = displayElement.querySelector("#start-recording");
      const stopButton = displayElement.querySelector("#stop-recording");
      const rerecordButton = displayElement.querySelector("#rerecord");
      const continueButton = displayElement.querySelector("#continue");
      const status = displayElement.querySelector("#recording-status");
      const playback = displayElement.querySelector("#playback");
      const timer = displayElement.querySelector("#timer");

      const setStatus = (message, state = "") => {
        status.textContent = message;
        status.className = `recording-status ${state}`.trim();
      };

      const updateTimer = () => {
        if (!recordingStartedAt) return;
        const elapsedSeconds = Math.floor((performance.now() - recordingStartedAt) / 1000);
        const minutes = String(Math.floor(elapsedSeconds / 60)).padStart(2, "0");
        const seconds = String(elapsedSeconds % 60).padStart(2, "0");
        timer.textContent = `${minutes}:${seconds}`;
        if (mediaRecorder && mediaRecorder.state === "recording") {
          window.requestAnimationFrame(updateTimer);
        }
      };

      const cleanupStream = () => {
        if (stream) {
          stream.getTracks().forEach((track) => track.stop());
          stream = null;
        }
      };

      const resetRecording = () => {
        chunks = [];
        currentBlob = null;
        if (currentAudio) {
          URL.revokeObjectURL(currentAudio);
          currentAudio = null;
        }
        playback.hidden = true;
        playback.removeAttribute("src");
        continueButton.disabled = true;
        rerecordButton.disabled = true;
        startButton.disabled = false;
        stopButton.disabled = true;
        timer.textContent = "00:00";
        setStatus("Ready.");
      };

      const stopRecording = () => {
        if (stopTimer) {
          window.clearTimeout(stopTimer);
          stopTimer = null;
        }
        if (mediaRecorder && mediaRecorder.state === "recording") {
          mediaRecorder.stop();
        }
      };

      startButton.addEventListener("click", async () => {
        resetRecording();
        startButton.disabled = true;
        setStatus("Opening microphone...");

        try {
          stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (error) {
          startButton.disabled = false;
          setStatus("Microphone access was blocked or unavailable. Please allow microphone access and try again.", "is-warning");
          return;
        }

        const mimeType = getSupportedMimeType();
        chunks = [];
        mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

        mediaRecorder.addEventListener("dataavailable", (event) => {
          if (event.data.size > 0) chunks.push(event.data);
        });

        mediaRecorder.addEventListener("stop", () => {
          const durationMs = Math.round(performance.now() - recordingStartedAt);
          cleanupStream();
          currentBlob = new Blob(chunks, { type: mediaRecorder.mimeType || "audio/webm" });
          currentAudio = URL.createObjectURL(currentBlob);
          playback.src = currentAudio;
          playback.hidden = false;
          stopButton.disabled = true;
          rerecordButton.disabled = !trial.allow_rerecord;

          if (durationMs < trial.min_duration_ms) {
            continueButton.disabled = true;
            startButton.disabled = false;
            setStatus("That recording was very short. Please record the full utterance again.", "is-warning");
            return;
          }

          continueButton.disabled = false;
          setStatus("Recording saved. Listen back, re-record, or continue.");
        });

        mediaRecorder.start();
        recordingStartedAt = performance.now();
        stopButton.disabled = false;
        setStatus("Recording...", "is-recording");
        updateTimer();

        stopTimer = window.setTimeout(() => {
          setStatus("Maximum recording length reached. Saving recording...");
          stopRecording();
        }, trial.max_duration_ms);
      });

      stopButton.addEventListener("click", stopRecording);
      rerecordButton.addEventListener("click", resetRecording);

      continueButton.addEventListener("click", async () => {
        continueButton.disabled = true;
        setStatus("Preparing recording...");

        const extension = getAudioExtension(currentBlob.type);
        const participantId = safeFilenamePart(trial.participant_id || "unknown_participant");
        const utteranceId = safeFilenamePart(trial.utterance_id || "utterance");
        const recordingId = `${participantId}_${utteranceId}`;
        const audioFilename = `${recordingId}.${extension}`;
        window.RecordingStore = window.RecordingStore || new Map();
        window.RecordingStore.set(recordingId, {
          blob: currentBlob,
          filename: audioFilename,
        });

        const trialData = {
          task: "voice_recording",
          utterance_id: trial.utterance_id,
          utterance_text: trial.utterance_text,
          recording_id: recordingId,
          audio_filename: audioFilename,
          audio_mime_type: currentBlob.type,
          audio_size_bytes: currentBlob.size,
          recording_duration_ms: Math.round(performance.now() - recordingStartedAt),
        };

        cleanupStream();
        this.jsPsych.finishTrial(trialData);
      });
    }
  }

  function getSupportedMimeType() {
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
      "audio/ogg;codecs=opus",
    ];
    return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
  }

  function getAudioExtension(mimeType) {
    if (mimeType.includes("mp4")) return "m4a";
    if (mimeType.includes("ogg")) return "ogg";
    if (mimeType.includes("wav")) return "wav";
    return "webm";
  }

  function safeFilenamePart(value) {
    return String(value).replace(/[^a-zA-Z0-9_-]/g, "_");
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;
  }

  window.RecordAudioTrialPlugin = RecordAudioTrialPlugin;
  window.RecordAudioTrialPlugin.info = info;
})();
