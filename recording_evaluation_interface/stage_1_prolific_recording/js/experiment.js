(async function () {
  const SAVE_ENDPOINT = "save-recording.cgi";
  const experimentMode = getExperimentMode();
  const PROLIFIC_COMPLETION_CODE = "<PROLIFIC_COMPLETION_CODE>";
  const COMPLETION_URL = getCompletionUrl();
  const participantInfoSheetHtml = await loadParticipantInfoSheet();
  const consentState = {
    hasConsented: null,
  };

  const jsPsych = initJsPsych({
    show_progress_bar: true,
    auto_update_progress_bar: true,
    on_finish: async () => {
      await handleFinish(jsPsych);
    },
  });

  const participantInfo = getParticipantInfo();
  jsPsych.data.addProperties({
    participant_id: participantInfo.participant_id,
    prolific_pid: participantInfo.prolific_pid,
    study_id: participantInfo.study_id,
    session_id: participantInfo.session_id,
    source: participantInfo.source,
    user_agent: navigator.userAgent,
    started_at: new Date().toISOString(),
    experiment_mode: experimentMode.mode,
    utterances_file: experimentMode.utterancesFile,
  });

  const utterances = await loadUtterances();
  const timeline = [];

  timeline.push({
    type: jsPsychHtmlButtonResponse,
    stimulus: `
      <section class="page-panel">
        <h1>Voice Recording Task</h1>
        <p>You will read a short set of sentences aloud. Each sentence is recorded separately.</p>
        <p class="notice">Please use a quiet room, keep your microphone close, and use headphones if possible.</p>
        ${experimentMode.isDebug ? '<p class="permission-help">Debug mode is active. The experiment will use the shortened debug utterance set.</p>' : ''}
      </section>
    `,
    choices: ["Begin"],
  });

  timeline.push({
    type: jsPsychHtmlButtonResponse,
    stimulus: `
      <section class="page-panel">
        <h1>Consent Form</h1>
        <p>Please read the Participant Information Sheet below before deciding whether to continue.</p>
        <p><a href="assets/20230322_PIS_Informatics.docx" download>Download the original Participant Information Sheet (.docx)</a></p>
        ${participantInfoSheetHtml}
      </section>
    `,
    choices: [
      "I consent to my recording being used for academic research",
      "I do not consent",
    ],
    data: { task: "consent" },
    on_finish: (data) => {
      const hasConsented = data.response === 0;
      consentState.hasConsented = hasConsented;
      data.consent_given = hasConsented;
      jsPsych.data.addProperties({ consent_given: hasConsented });
    },
  });

  const studyTimeline = [];

  studyTimeline.push({
    type: jsPsychSurveyHtmlForm,
    preamble: `
      <section class="page-panel">
        <h2>Participant ID</h2>
        <p>If you joined from Prolific, this should be automatically filled in. If it is blank, please enter your Prolific ID.</p>
      </section>
    `,
    html: `
      <div class="page-panel">
        <label>Prolific ID
          <input
            name="prolific_pid"
            type="text"
            value="${escapeAttribute(participantInfo.prolific_pid)}"
            autocomplete="off"
          >
        </label>
      </div>
    `,
    button_label: "Continue",
    data: { task: "participant_id_question" },
    on_finish: (data) => {
      const response = data.response || {};
      const prolificPid = (response.prolific_pid || "").trim();
      if (!prolificPid) return;

      participantInfo.participant_id = prolificPid;
      participantInfo.prolific_pid = prolificPid;
      participantInfo.source = "prolific_or_manual";
      jsPsych.data.addProperties({
        participant_id: participantInfo.participant_id,
        prolific_pid: participantInfo.prolific_pid,
        source: participantInfo.source,
      });
    },
  });

  studyTimeline.push({
    type: jsPsychSurveyHtmlForm,
    preamble: `
      <section class="page-panel">
        <h2>Before Recording</h2>
        <p>These details help us interpret the recordings.</p>
      </section>
    `,
    html: `
      <div class="page-panel">
        <div class="form-grid form-grid-three">
          <label>Age
            <input name="age" type="number" min="18" max="100" inputmode="numeric" required>
          </label>
          <label>Gender
            <select name="gender" required>
              <option value="">Select one</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="non_binary">Non-binary</option>
              <option value="other">Other</option>
              <option value="prefer_not_to_say">Prefer not to say</option>
            </select>
          </label>
          <label>Ethnicity
            <input name="ethnicity" type="text" required>
          </label>
          <label>Native/First language
            <input name="first_native_language" type="text" autocomplete="language" required>
          </label>
          <label>Other languages/dialects spoken
            <input name="other_languages" type="text" autocomplete="language" required>
          </label>
          <label>Describe your own English accent
            <input name="english_accent_description" type="text" required>
          </label>
          <label>Current area of residence (in the format of City, Country)
            <input name="current_area_residence" type="text" autocomplete="address-level2" required>
          </label>
          <label>Area of most time spent before adulthood (in the format of City, Country)
            <input name="area_most_time_spent_before_adulthood" type="text" autocomplete="address-level2" required>
          </label>
          <label>Area of most time spent after adulthood (in the format of City, Country)
            <input name="area_most_time_spent_after_adulthood" type="text" autocomplete="address-level2" required>
          </label>
          <label>Other areas stayed for more than two years (in the format of City1, Country1; City2, Country2; ...)
            <input name="other_areas_stayed" type="text" autocomplete="address-level2" required>
          </label>
          <label>Recording device
            <select name="recording_device" required>
              <option value="">Select one</option>
              <option value="laptop_microphone">Laptop microphone</option>
              <option value="phone_microphone">Phone microphone</option>
              <option value="headset_microphone">Headset microphone</option>
              <option value="external_microphone">External microphone</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label>Specific recording device (e.g. built-in Lenovo laptop microphone, AirPods, iPhone X microphone)
            <input name="recording_device_detail" type="text" required>
          </label>
        </div>
      </div>
    `,
    button_label: "Continue",
    data: { task: "background_questions" },
  });

  studyTimeline.push({
    type: MicrophoneCheckTrialPlugin,
  });

  utterances.forEach((utterance, index) => {
    studyTimeline.push({
      type: RecordAudioTrialPlugin,
      participant_id: () => participantInfo.participant_id,
      utterance_id: utterance.id,
      utterance_text: utterance.text,
      trial_number: index + 1,
      total_trials: utterances.length,
      min_duration_ms: 800,
      max_duration_ms: 30000,
      allow_rerecord: true,
    });
  });

  studyTimeline.push({
    type: jsPsychHtmlButtonResponse,
    stimulus: `
      <section class="page-panel">
        <h2>Finished</h2>
        <p>Thank you! Your recordings are ready now. Please click the button below to submit your responses. Upon submission, you will also be redirected to Prolific study completion link to mark your successful completion. We look forward to your participation in the second stage.</p>
      </section>
    `,
    choices: ["Submit"],
  });

  timeline.push({
    timeline: studyTimeline,
    conditional_function: () => consentState.hasConsented === true,
  });

  timeline.push({
    timeline: [
      {
        type: jsPsychHtmlKeyboardResponse,
        stimulus: `
          <section class="page-panel">
            <h1>Please return your submission on Prolific.</h1>
          </section>
        `,
        choices: "NO_KEYS",
        data: { task: "no_consent_exit" },
      },
    ],
    conditional_function: () => consentState.hasConsented === false,
  });

  jsPsych.run(timeline);

  async function loadParticipantInfoSheet() {
    const response = await fetch("assets/pis-content.html", { cache: "no-store" });
    if (!response.ok) {
      return `
        <div class="permission-help">
          <p>The Participant Information Sheet could not be loaded inline. Please download and read the original document before continuing.</p>
        </div>
      `;
    }
    return response.text();
  }

  async function loadUtterances() {
    const response = await fetch(experimentMode.utterancesFile, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Could not load utterances: ${response.status}`);
    }
    return response.json();
  }

  function getExperimentMode() {
    const params = new URLSearchParams(window.location.search);
    const debugValue = (params.get("debug") || "").toLowerCase();
    const modeValue = (params.get("mode") || "").toLowerCase();
    const isDebug = ["1", "true", "yes"].includes(debugValue) || modeValue === "debug";

    return {
      isDebug,
      mode: isDebug ? "debug" : "full",
      utterancesFile: isDebug ? "data/utterances_debug.json" : "data/utterances.json",
    };
  }

  function getParticipantInfo() {
    const params = new URLSearchParams(window.location.search);
    const prolificPid = params.get("PROLIFIC_PID") || "";
    return {
      participant_id: prolificPid || crypto.randomUUID(),
      prolific_pid: prolificPid,
      study_id: params.get("STUDY_ID") || "",
      session_id: params.get("SESSION_ID") || "",
      source: prolificPid ? "prolific" : "local_or_direct",
    };
  }

  async function handleFinish(instance) {
    if (consentState.hasConsented === false) {
      return;
    }

    const exportedAt = new Date().toISOString();
    const payload = {
      exported_at: exportedAt,
      participant: participantInfo,
      data: instance.data.get().values(),
    };

    let savedRemotely = false;
    let uploadError = null;

    if (SAVE_ENDPOINT) {
      try {
        savedRemotely = await uploadExperimentData(payload);
      } catch (error) {
        uploadError = error;
        console.error("Could not upload experiment data.", error);
      }
    }

    if (!savedRemotely) {
      if (experimentMode.isDebug) {
        showDebugUploadError(uploadError);
        return;
      }
      await downloadExperimentData(payload);
      showProductionUploadError(uploadError);
      return;
    }

    if (COMPLETION_URL) {
      // Give the browser time to start the participant-initiated download.
      await new Promise((resolve) => window.setTimeout(resolve, 750));
      window.location.replace(COMPLETION_URL);
    }
  }

  function showDebugUploadError(error) {
    const displayElement = document.querySelector("#jspsych-content") || document.body;
    const message = error instanceof Error ? error.message : "Unknown upload error";
    displayElement.innerHTML = `
      <section class="page-panel">
        <h2>Debug upload failed</h2>
        <p>No local backup was downloaded because debug mode is configured for server uploads only.</p>
        <p class="permission-help"><strong>Server error:</strong> ${escapeHtml(message)}</p>
        <p>Correct the CGI/backend problem, then restart the debug experiment.</p>
      </section>
    `;
  }

  function showProductionUploadError(error) {
    const displayElement = document.querySelector("#jspsych-content") || document.body;
    const message = error instanceof Error ? error.message : "Unknown upload error";
    displayElement.innerHTML = `
      <section class="page-panel">
        <h2>Your data could not be uploaded</h2>
        <p>A backup ZIP file containing your JSON data and audio recordings has been downloaded to your device.</p>
        <p><strong>Please email the downloaded ZIP file to <a href="mailto:jinzuomu.zhong@ed.ac.uk">jinzuomu.zhong@ed.ac.uk</a>.</strong></p>
        <p class="permission-help">Please keep the downloaded file until the researcher confirms receipt.</p>
        <p class="permission-help"><strong>Upload error:</strong> ${escapeHtml(message)}</p>
      </section>
    `;
  }

  function getCompletionUrl() {
    if (experimentMode.isDebug) {
      return "https://www.nytimes.com/";
    }

    const params = new URLSearchParams(window.location.search);
    const completionCode = params.get("COMPLETION_CODE") || PROLIFIC_COMPLETION_CODE;
    return `https://app.prolific.com/submissions/complete?cc=${encodeURIComponent(completionCode)}`;
  }

  async function uploadExperimentData(payload) {
    const recordings = window.RecordingStore || new Map();
    const recordingTrials = payload.data.filter(
      (trial) => trial.task === "voice_recording" && trial.recording_id
    );

    if (recordings.size !== recordingTrials.length || recordings.size === 0) {
      throw new Error(
        `Expected ${recordingTrials.length} recordings but found ${recordings.size} in memory.`
      );
    }

    // Upload one recording per request. The full study contains 34 recordings,
    // and keeps every CGI request small and independently retryable.
    for (const trial of recordingTrials) {
      const recording = recordings.get(trial.recording_id);
      if (!recording) {
        throw new Error(`Missing recording for ${trial.recording_id}.`);
      }

      const recordingForm = new FormData();
      recordingForm.append("action", "recording");
      recordingForm.append("participant_id", payload.participant.participant_id);
      recordingForm.append("recording", recording.blob, recording.filename);
      await postUploadForm(recordingForm);
    }

    const metadataForm = new FormData();
    metadataForm.append("action", "metadata");
    metadataForm.append("participant_id", payload.participant.participant_id);
    metadataForm.append("metadata", JSON.stringify(payload, null, 2));
    metadataForm.append("metadata_filename", getMetadataFilename(payload.participant.participant_id));
    await postUploadForm(metadataForm);

    return true;
  }

  async function postUploadForm(formData) {
    const response = await fetch(SAVE_ENDPOINT, {
      method: "POST",
      body: formData,
    });

    const responseText = await response.text();
    let result;
    try {
      result = JSON.parse(responseText);
    } catch (error) {
      throw new Error(`Upload endpoint returned invalid JSON (HTTP ${response.status}).`);
    }

    if (!response.ok || result.ok !== true) {
      throw new Error(result.error || `Upload failed with HTTP ${response.status}.`);
    }

    return result;
  }

  async function downloadExperimentData(payload) {
    if (typeof JSZip === "undefined") {
      throw new Error("JSZip is unavailable; could not prepare the backup download.");
    }

    const zip = new JSZip();
    const metadataFilename = getMetadataFilename(payload.participant.participant_id);
    zip.file(metadataFilename, JSON.stringify(payload, null, 2));
    const recordings = window.RecordingStore || new Map();
    recordings.forEach((recording) => {
      zip.file(recording.filename, recording.blob);
    });

    const zipBlob = await zip.generateAsync({ type: "blob" });
    const safeId = safeFilenamePart(payload.participant.participant_id);
    const zipFilename = `recording_${safeId}_${Date.now()}.zip`;
    const url = URL.createObjectURL(zipBlob);

    await new Promise((resolve) => {
      const displayElement = document.querySelector("#jspsych-content") || document.body;
      displayElement.innerHTML = `
        <section class="page-panel">
          <h2>Download your recording backup</h2>
          <p>The server upload was unsuccessful. Your JSON data and ${recordings.size} recording file(s) have been prepared in one ZIP archive.</p>
          <p>Please click the button below. You will be redirected after the download starts.</p>
          <a id="download-backup" class="jspsych-btn" href="${url}" download="${zipFilename}">Download backup and continue</a>
        </section>
      `;

      const downloadLink = document.querySelector("#download-backup");
      downloadLink.addEventListener("click", () => {
        downloadLink.textContent = "Download started…";
        downloadLink.style.pointerEvents = "none";
        window.setTimeout(() => URL.revokeObjectURL(url), 60000);
        resolve();
      }, { once: true });
    });
  }

  function getMetadataFilename(participantId) {
    const safeId = safeFilenamePart(participantId);
    return `recording_${safeId}_${Date.now()}.json`;
  }

  function safeFilenamePart(value) {
    return String(value).replace(/[^a-zA-Z0-9_-]/g, "_");
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = String(value);
    return div.innerHTML;
  }

  function escapeAttribute(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }
})();
