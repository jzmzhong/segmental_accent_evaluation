(async function () {
  const SAVE_ENDPOINT = "save-responses.cgi";
  const experimentMode = getExperimentMode();
  const previewMode = new URLSearchParams(window.location.search).get("preview") || "";
  const isQuestionPreview = previewMode === "question";
  const content = await loadJson("data/content.json");
  const audioManifest = await loadJson("data/audio_manifest.json");
  const participantInfo = getParticipantInfo();
  const audioSpeaker = resolveAudioSpeaker(participantInfo, content.experiment_config);
  const audioSpeakerId = audioSpeaker.id;
  const audioDirectory = getAudioDirectory(audioSpeakerId);
  const participantInfoSheetHtml = await loadParticipantInfoSheet();
  const utterances = await loadJson("data/utterances_segmented.json");
  const audioFilenames = await discoverAudioFilenames(audioDirectory, audioManifest, audioSpeakerId);
  const modeUtterances = experimentMode.isDebug ? utterances.slice(0, 2) : utterances;
  const regularTrialSpecs = createRegularTrialSpecs(
    modeUtterances,
    content.experiment_config.regular_trial_systems
  );
  const attentionCheckCount = content.attention_checks.cross_speaker_utterance_ids.length;
  const totalQuestionCount = regularTrialSpecs.length + attentionCheckCount;
  const consentState = { hasConsented: isQuestionPreview ? true : null };

  const jsPsych = initJsPsych({
    show_progress_bar: true,
    auto_update_progress_bar: true,
    on_finish: async () => {
      await handleFinish(jsPsych);
    },
  });

  jsPsych.data.addProperties({
    participant_id: participantInfo.participant_id,
    prolific_pid: participantInfo.prolific_pid,
    study_id: participantInfo.study_id,
    session_id: participantInfo.session_id,
    target_speaker: participantInfo.target_speaker,
    audio_speaker_id: audioSpeakerId,
    audio_speaker_source: audioSpeaker.source,
    source: participantInfo.source,
    experiment_mode: experimentMode.mode,
    utterance_count: totalQuestionCount,
    experimental_utterance_count: regularTrialSpecs.length,
    attention_check_count: attentionCheckCount,
    trials_randomized: Boolean(content.experiment_config.randomize_trials),
    user_agent: navigator.userAgent,
    started_at: new Date().toISOString(),
  });

  const timeline = [];

  if (!isQuestionPreview) {
    timeline.push({
      type: jsPsychHtmlButtonResponse,
      stimulus: `
        <section class="page-panel">
          <h1>${content.instruction_page.title}</h1>
          ${content.instruction_page.paragraphs.map((paragraph) => `<p>${paragraph}</p>`).join("")}
          <p class="notice">${content.instruction_page.notice}</p>
          <p>${content.instruction_page.question_count.replace("{question_count}", totalQuestionCount)}</p>
        </section>
      `,
      choices: [content.instruction_page.button],
      data: { task: "welcome" },
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
  }

  const participantIdTrial = {
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
            required
          >
        </label>
      </div>
    `,
    button_label: "Continue",
    data: { task: "participant_id_question" },
    on_finish: (data) => {
      const prolificPid = ((data.response || {}).prolific_pid || "").trim();
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
  };

  const demographicsTrial = {
    type: jsPsychSurveyHtmlForm,
    preamble: `
      <section class="page-panel">
        <h2>Before the Evaluation</h2>
        <p>These details help us interpret your responses.</p>
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
  };

  const conditionalDemographicsTrial = {
    timeline: [demographicsTrial],
    conditional_function: () => !isApprovedProlificParticipant(
      participantInfo.prolific_pid,
      content.experiment_config
    ),
  };

  const demonstrationUtterances = utterances.slice(1, 3);
  const demonstrationSpeakerId = "testparticipant";
  const demonstrationDirectory = getAudioDirectory(demonstrationSpeakerId);
  const demonstrationFilenames = Array.isArray(audioManifest[demonstrationSpeakerId])
    ? audioManifest[demonstrationSpeakerId]
    : [];
  const demonstrationTrial = createAnnotationDemonstrationTrial(
    demonstrationUtterances,
    demonstrationSpeakerId,
    demonstrationFilenames,
    demonstrationDirectory
  );

  const attentionCheckSpecs = content.attention_checks.cross_speaker_utterance_ids.map(
    (utteranceId) => {
      const utterance = findUtterance(utteranceId);
      return {
        utterance,
        options: {
          task: "attention_check",
          attentionCheckType: `cross_speaker_${utterance.id}`,
          evaluationSystem: "cross_speaker_ground_truth",
          trialId: `${utterance.id}_cross_speaker`,
          referenceFilename: `testparticipant_${utterance.id}.wav`,
          referenceDirectory: demonstrationDirectory,
          referenceFilenames: demonstrationFilenames,
          candidateFilename: `${audioSpeakerId}_${utterance.id}.wav`,
        },
      };
    }
  );
  const trialSpecs = content.experiment_config.randomize_trials
    ? shuffleCopy([...regularTrialSpecs, ...attentionCheckSpecs])
    : [...regularTrialSpecs, ...attentionCheckSpecs];
  const allEvaluationTrials = trialSpecs.map((spec, index) =>
    createEvaluationTrial(
      spec.utterance,
      index,
      trialSpecs.length,
      audioFilenames,
      audioSpeakerId,
      audioDirectory,
      spec.options || {}
    )
  );
  const previewSpec = regularTrialSpecs[Math.floor(Math.random() * regularTrialSpecs.length)];
  const randomPreviewTrial = createEvaluationTrial(
    previewSpec.utterance,
    0,
    1,
    audioFilenames,
    audioSpeakerId,
    audioDirectory,
    previewSpec.options
  );
  const finalFeedbackTrial = createFinalFeedbackTrial();

  const studyTimeline = isQuestionPreview
    ? [randomPreviewTrial]
    : [
        participantIdTrial,
        conditionalDemographicsTrial,
        demonstrationTrial,
        ...allEvaluationTrials,
        finalFeedbackTrial,
      ];

  timeline.push({
    timeline: studyTimeline,
    conditional_function: () => consentState.hasConsented === true,
  });

  timeline.push({
    timeline: [{
      type: jsPsychHtmlKeyboardResponse,
      stimulus: `
        <section class="page-panel">
          <h1>Please return your submission on Prolific.</h1>
        </section>
      `,
      choices: "NO_KEYS",
      data: { task: "no_consent_exit" },
    }],
    conditional_function: () => consentState.hasConsented === false,
  });

  jsPsych.run(timeline);

  function createEvaluationTrial(utterance, index, total, filenames, speakerId, directory, options = {}) {
    const referenceFilename = options.referenceFilename || `${speakerId}_${utterance.id}.wav`;
    const candidateFilename = Object.hasOwn(options, "candidateFilename")
      ? options.candidateFilename
      : findCandidateFilename(speakerId, utterance.id, filenames);
    const referenceDirectory = options.referenceDirectory || directory;
    const candidateDirectory = options.candidateDirectory || directory;
    const referenceFilenames = options.referenceFilenames || filenames;
    const candidateFilenames = options.candidateFilenames || filenames;
    const referenceAudioAvailable = referenceFilenames.includes(referenceFilename);
    const candidateAudioAvailable = candidateFilenames.includes(candidateFilename);
    const questionNumber = index + 1;

    return {
      type: jsPsychSurveyHtmlForm,
      preamble: `
        <section class="page-panel evaluation-panel">
          <p class="question-counter">Question ${questionNumber} of ${total}</p>
          <h1>${options.title || content.question_page.title}</h1>
          <p>${content.question_page.introduction}</p>

          <div class="audio-comparison">
            ${renderAudioPlayer(
              content.question_page.reference_audio_label,
              referenceAudioAvailable ? referenceFilename : "",
              utterance.id,
              referenceDirectory,
              content.question_page.missing_reference_audio,
              `${referenceDirectory}${referenceFilename}`
            )}
            ${renderAudioPlayer(
              content.question_page.candidate_audio_label,
              candidateAudioAvailable ? candidateFilename : "",
              utterance.id,
              candidateDirectory,
              content.question_page.missing_candidate_audio,
              `${candidateDirectory}${candidateFilename || `cloned_${speakerId}_${utterance.id}_ref_*.wav`}`
            )}
          </div>
        </section>
      `,
      html: `
        <section class="page-panel evaluation-panel">
          ${renderRatingQuestion(
            "speaker_rating",
            content.question_page.speaker_rating.title,
            content.question_page.speaker_rating.instruction,
            content.question_page.speaker_rating.low_label,
            content.question_page.speaker_rating.high_label
          )}

          ${renderRatingQuestion(
            "accent_rating",
            content.question_page.accent_rating.title,
            content.question_page.accent_rating.instruction,
            content.question_page.accent_rating.low_label,
            content.question_page.accent_rating.high_label
          )}

          <fieldset class="annotation-fieldset">
            <legend>${content.question_page.annotation.title}</legend>
            ${content.question_page.annotation.paragraphs.map((paragraph) => `<p>${paragraph}</p>`).join("")}
            <div class="annotation-sentence" aria-label="Sentence segments to annotate">
              ${renderAnnotationTokens(utterance.text)}
            </div>
            <p id="annotation-limit-status" class="annotation-limit-status" aria-live="polite"></p>
          </fieldset>
        </section>
      `,
      button_label: content.question_page.submit_button,
      on_load: () => {
        setupAnnotationLimit(content.question_page.annotation.max_parts);
      },
      data: {
        task: options.task || "speaker_and_accent_similarity",
        attention_check_type: options.attentionCheckType || "",
        response_type: "speaker_and_accent_smos_rpt",
        trial_order: questionNumber,
        question_id: utterance.id,
        trial_id: options.trialId || utterance.id,
        evaluation_system: options.evaluationSystem || "",
        reference_speech: referenceFilename,
        candidate_speech: candidateFilename || "",
        segmented_text: utterance.text,
        sentence: utterance.text.replaceAll("|", ""),
        reference_audio_available: referenceAudioAvailable,
        candidate_audio_available: candidateAudioAvailable,
        audio_speaker_id: speakerId,
      },
      on_finish: (data) => {
        const response = data.response || {};
        const selectedClues = Object.entries(response)
          .filter(([name, value]) => name.startsWith("accent_clue_") && value !== false && value != null)
          .map(([, value]) => value);

        data.speaker_rating = Number(response.speaker_rating);
        data.accent_rating = Number(response.accent_rating);
        data.rating = data.accent_rating;
        const annotationIndices = [...new Set(selectedClues.map(Number))]
          .filter(Number.isInteger)
          .sort((a, b) => a - b)
          .slice(0, content.question_page.annotation.max_parts);

        data.annotation = annotationIndices.join("|");
      },
    };
  }

  function createFinalFeedbackTrial() {
    return {
      type: jsPsychSurveyHtmlForm,
      preamble: `
        <section class="page-panel">
          <h1>${content.final_feedback_page.title}</h1>
          <p>${content.final_feedback_page.introduction}</p>
        </section>
      `,
      html: `
        <section class="page-panel evaluation-panel">
          ${renderRatingQuestion(
            "similarity_task_difficulty",
            content.final_feedback_page.similarity_difficulty.title,
            content.final_feedback_page.similarity_difficulty.instruction,
            content.final_feedback_page.low_label,
            content.final_feedback_page.high_label
          )}

          ${renderRatingQuestion(
            "annotation_task_difficulty",
            content.final_feedback_page.annotation_difficulty.title,
            content.final_feedback_page.annotation_difficulty.instruction,
            content.final_feedback_page.low_label,
            content.final_feedback_page.high_label
          )}

          <fieldset class="annotation-fieldset final-comments-fieldset">
            <legend>${content.final_feedback_page.comments.title}</legend>
            <p>${content.final_feedback_page.comments.instruction}</p>
            <textarea
              class="final-comments"
              name="task_comments"
              rows="6"
              required
              placeholder="${escapeAttribute(content.final_feedback_page.comments.placeholder)}"
            ></textarea>
          </fieldset>
        </section>
      `,
      button_label: content.final_feedback_page.submit_button,
      data: { task: "final_task_feedback" },
      on_finish: (data) => {
        const response = data.response || {};
        data.similarity_task_difficulty = Number(response.similarity_task_difficulty);
        data.annotation_task_difficulty = Number(response.annotation_task_difficulty);
        data.task_comments = String(response.task_comments || "").trim();
      },
    };
  }

  function createAnnotationDemonstrationTrial(utteranceItems, speakerId, filenames, directory) {
    const examples = utteranceItems.map((utterance, exampleIndex) => {
      const referenceFilename = `${speakerId}_${utterance.id}.wav`;
      const candidateFilename = findCandidateFilename(speakerId, utterance.id, filenames);

      return `
        <section class="page-panel evaluation-panel demonstration-example">
          <h2>${content.demonstration_page.example_label.replace("{number}", exampleIndex + 1)}</h2>
          <div class="audio-comparison">
            ${renderAudioPlayer(
              content.question_page.reference_audio_label,
              filenames.includes(referenceFilename) ? referenceFilename : "",
              utterance.id,
              directory,
              content.question_page.missing_reference_audio,
              `${directory}${referenceFilename}`
            )}
            ${renderAudioPlayer(
              content.question_page.candidate_audio_label,
              candidateFilename,
              utterance.id,
              directory,
              content.question_page.missing_candidate_audio,
              `${directory}cloned_${speakerId}_${utterance.id}_ref_*.wav`
            )}
          </div>
          <div class="annotation-sentence" aria-label="Practice sentence ${exampleIndex + 1} segments">
            ${renderAnnotationTokens(utterance.text, `demo_${exampleIndex}_clue`)}
          </div>
        </section>
      `;
    }).join("");

    return {
      type: jsPsychSurveyHtmlForm,
      preamble: `
        <section class="page-panel">
          <h1>${content.demonstration_page.title}</h1>
          ${content.demonstration_page.paragraphs.map((paragraph) => `<p>${paragraph}</p>`).join("")}
          <div class="demonstration-guidelines">
            <h2>${content.question_page.annotation.title}</h2>
            ${content.question_page.annotation.paragraphs.map((paragraph) => `<p>${paragraph}</p>`).join("")}
          </div>
        </section>
      `,
      html: `
        ${examples}
        <section class="page-panel demonstration-answer-controls">
          <button type="button" id="show-demonstration-answers" class="jspsych-btn">
            ${content.demonstration_page.show_answer_button}
          </button>
          <p id="demonstration-answer-message" class="demonstration-answer-message" hidden>
            ${content.demonstration_page.answer_message}
          </p>
        </section>
      `,
      button_label: content.demonstration_page.button,
      data: {
        task: "annotation_demonstration",
        audio_speaker_id: speakerId,
        question_ids: utteranceItems.map((utterance) => utterance.id),
      },
      on_load: () => {
        const form = document.querySelector("#jspsych-survey-html-form");
        const continueButton = form?.querySelector('button[type="submit"], input[type="submit"]');
        const showAnswerButton = document.querySelector("#show-demonstration-answers");
        const answerMessage = document.querySelector("#demonstration-answer-message");

        if (continueButton) continueButton.disabled = true;
        showAnswerButton?.addEventListener("click", () => {
          utteranceItems.forEach((utterance, exampleIndex) => {
            const answerIndices = content.demonstration_page.answers?.[utterance.id] || [];
            answerIndices.forEach((segmentIndex) => {
              const answerInput = form?.querySelector(
                `input[name="demo_${exampleIndex}_clue_${segmentIndex}"]`
              );
              answerInput?.closest(".annotation-token")?.classList.add("demonstration-answer");
            });
          });

          if (answerMessage) answerMessage.hidden = false;
          if (continueButton) continueButton.disabled = false;
          showAnswerButton.disabled = true;
          showAnswerButton.textContent = content.demonstration_page.answers_shown_button;
        });
      },
      on_finish: (data) => {
        const response = data.response || {};
        data.annotations = utteranceItems.map((utterance, exampleIndex) => {
          const prefix = `demo_${exampleIndex}_clue_`;
          const indices = Object.entries(response)
            .filter(([name, value]) => name.startsWith(prefix) && value !== false && value != null)
            .map(([, value]) => Number(value))
            .filter(Number.isInteger)
            .sort((a, b) => a - b);

          return {
            question_id: utterance.id,
            annotation: [...new Set(indices)].join("|"),
          };
        });
      },
    };
  }

  function renderAudioPlayer(
    label,
    filename,
    utteranceId = "",
    directory = "",
    missingMessage = "",
    attemptedPath = ""
  ) {
    if (!filename) {
      return `
        <div class="audio-missing" role="status">
          <strong>${label}</strong>
          <span>${missingMessage.replace("{utterance_id}", escapeHtml(utteranceId))}</span>
          <code class="audio-missing-path">${escapeHtml(attemptedPath)}</code>
        </div>
      `;
    }

    return `
      <label>
        <span>${label}</span>
        <audio controls preload="metadata">
          <source src="${directory}${encodeURIComponent(filename)}" type="audio/wav">
        </audio>
      </label>
    `;
  }

  function renderRatingQuestion(name, legend, instruction, lowLabel, highLabel) {
    return `
      <fieldset class="rating-fieldset">
        <legend>${legend}</legend>
        <p class="rating-instruction">${instruction}</p>
        <div class="rating-scale">
          ${[1, 2, 3, 4, 5].map((rating) => `
            <label class="rating-option">
              <input type="radio" name="${name}" value="${rating}" required>
              <span class="rating-number">${rating}</span>
              <span>${rating === 1 ? lowLabel : rating === 5 ? highLabel : ""}</span>
            </label>
          `).join("")}
        </div>
      </fieldset>
    `;
  }

  function renderAnnotationTokens(segmentedText, inputPrefix = "accent_clue") {
    const segments = segmentedText.split("|");

    return segments.map((segment, index) => {
      const renderedSegment = segment.split(/(\s+)/).map((part) => {
        if (!part) return "";
        if (/^\s+$/.test(part)) {
          const visibleSpaces = Array.from(part).map(() => "&nbsp;").join("");
          return `<span class="annotation-space" aria-hidden="true">${visibleSpaces}</span>`;
        }
        if (/^[,.!?;:'"“”‘’\-–—]+$/.test(part)) {
          return `<span class="annotation-unselectable">${escapeHtml(part)}</span>`;
        }

        return `
          <label class="annotation-token">
            <input type="checkbox" name="${inputPrefix}_${index}" value="${index}">
            <span>${escapeHtml(part)}</span>
          </label>
        `;
      }).join("");

      const nextSegment = segments[index + 1] || "";
      const showBoundary = index < segments.length - 1 &&
        segment.length > 0 &&
        nextSegment.length > 0 &&
        !/\s$/.test(segment) &&
        !/^\s/.test(nextSegment) &&
        /^[A-Za-z0-9]/.test(nextSegment);

      return renderedSegment + (showBoundary
        ? '<span class="annotation-boundary" aria-hidden="true">·</span>'
        : "");
    }).join("");
  }

  function setupAnnotationLimit(configuredMaximum) {
    const maximum = Number.isInteger(configuredMaximum) && configuredMaximum > 0
      ? configuredMaximum
      : 10;
    const inputs = [...document.querySelectorAll('input[name^="accent_clue_"]')];
    const status = document.querySelector("#annotation-limit-status");

    const update = () => {
      const selectedCount = inputs.filter((input) => input.checked).length;
      const atLimit = selectedCount >= maximum;
      inputs.forEach((input) => {
        input.disabled = atLimit && !input.checked;
      });
      if (status) {
        status.textContent = atLimit
          ? `${selectedCount} parts selected. Deselect one part before choosing another.`
          : `${selectedCount} parts selected.`;
        status.classList.toggle("at-limit", atLimit);
      }
    };

    inputs.forEach((input) => input.addEventListener("change", update));
    update();
  }

  function findCandidateFilename(speakerId, utteranceId, filenames, system = "") {
    const expectedPrefix = `cloned_${speakerId}_${utteranceId}`.toLowerCase();
    return filenames.find((filename) => {
      const lower = filename.toLowerCase();
      const matchesSystem = !system || lower.endsWith(`_${system.toLowerCase()}.wav`);
      return lower.endsWith(".wav") &&
        matchesSystem &&
        (lower === `${expectedPrefix}.wav` || lower.startsWith(`${expectedPrefix}_ref_`));
    }) || "";
  }

  function createRegularTrialSpecs(utteranceItems, systemLimits) {
    const configuredSystems = systemLimits && typeof systemLimits === "object"
      ? Object.entries(systemLimits)
      : [];

    if (configuredSystems.length === 0) {
      throw new Error("experiment_config.regular_trial_systems must define at least one system.");
    }

    return configuredSystems.flatMap(([system, configuredValue]) => {
      const configuredLimit = Number(configuredValue);
      const limit = Number.isInteger(configuredLimit) && configuredLimit >= 0
        ? configuredLimit
        : utteranceItems.length;

      return utteranceItems.slice(0, limit).map((utterance) => {
        const options = {
          evaluationSystem: system,
          trialId: `${utterance.id}_${system}`,
        };

        if (system === "ground_truth") {
          options.candidateFilename = `${audioSpeakerId}_${utterance.id}.wav`;
        } else {
          options.candidateFilename = findCandidateFilename(
            audioSpeakerId,
            utterance.id,
            audioFilenames,
            system
          );
        }

        return { utterance, options };
      });
    });
  }

  function findUtterance(utteranceId) {
    const utterance = utterances.find((item) => item.id === utteranceId);
    if (!utterance) throw new Error(`Unknown utterance ID: ${utteranceId}`);
    return utterance;
  }

  async function discoverAudioFilenames(directory, manifest, speakerId) {
    const manifestFilenames = manifest[speakerId];
    if (Array.isArray(manifestFilenames)) {
      return manifestFilenames;
    }

    try {
      const response = await fetch(directory, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const directoryHtml = await response.text();
      const documentFragment = new DOMParser().parseFromString(directoryHtml, "text/html");
      return Array.from(documentFragment.querySelectorAll("a[href]"))
        .map((link) => decodeURIComponent(link.getAttribute("href").split("/").pop()))
        .filter((filename) => filename.toLowerCase().endsWith(".wav"));
    } catch (error) {
      console.error(`Could not discover audio filenames for ${speakerId}.`, error);
      return [];
    }
  }

  function getAudioDirectory(speakerId) {
    return `data/wav/${encodeURIComponent(speakerId)}/`;
  }

  async function loadParticipantInfoSheet() {
    try {
      const response = await fetch("assets/pis-content.html", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.text();
    } catch (error) {
      console.error("Could not load the Participant Information Sheet.", error);
      return `
        <div class="permission-help">
          <p>The Participant Information Sheet could not be loaded inline. Please download and read the original document before continuing.</p>
        </div>
      `;
    }
  }

  async function loadJson(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`Could not load ${path}: HTTP ${response.status}`);
    return response.json();
  }

  async function handleFinish(instance) {
    if (consentState.hasConsented === false) return;

    const payload = {
      exported_at: new Date().toISOString(),
      participant: { ...participantInfo },
      data: instance.data.get().values(),
    };
    const responseFilename = getResponseFilename(participantInfo.participant_id);

    if (isQuestionPreview) {
      downloadResponseBackup(payload, responseFilename);
      showSaveStatus(
        "Preview complete",
        "Preview data was downloaded locally and was not sent to the study server."
      );
      return;
    }

    try {
      const result = await uploadExperimentResponses(payload, responseFilename);
      showSaveStatus(
        "Responses saved",
        `Your responses were securely saved as <code>${escapeHtml(result.saved)}</code>.`
      );
      await redirectToCompletion();
    } catch (error) {
      console.error("Could not upload experiment responses; downloading a local backup.", error);
      downloadResponseBackup(payload, responseFilename);
      showSaveStatus(
        "Server upload failed",
        "A local JSON backup was downloaded. Please keep this file and contact the researcher if requested.",
        error
      );
    }
  }

  async function uploadExperimentResponses(payload, responseFilename) {
    const form = new FormData();
    form.append("participant_id", payload.participant.participant_id);
    form.append("responses", JSON.stringify(payload, null, 2));
    form.append("response_filename", responseFilename);

    const response = await fetch(SAVE_ENDPOINT, {
      method: "POST",
      body: form,
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

  function downloadResponseBackup(payload, filename) {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  function showSaveStatus(title, message, error = null) {
    const displayElement = document.querySelector("#jspsych-content") || document.body;
    const errorMessage = error instanceof Error
      ? `<p class="permission-help"><strong>Upload error:</strong> ${escapeHtml(error.message)}</p>`
      : "";
    displayElement.innerHTML = `
      <section class="page-panel">
        <h2>${title}</h2>
        <p>${message}</p>
        ${errorMessage}
      </section>
    `;
  }

  function getResponseFilename(participantId) {
    return `evaluation_${sanitiseFilename(participantId)}_${Date.now()}.json`;
  }

  async function redirectToCompletion() {
    const completionUrl = getCompletionUrl();
    if (!completionUrl) return;

    await new Promise((resolve) => window.setTimeout(resolve, 750));
    window.location.replace(completionUrl);
  }

  function getCompletionUrl() {
    if (isQuestionPreview) return "";
    if (experimentMode.isDebug) {
      return content.experiment_config.debug_completion_url;
    }

    const params = new URLSearchParams(window.location.search);
    const completionCode = params.get("COMPLETION_CODE") ||
      content.experiment_config.prolific_completion_code;
    return `https://app.prolific.com/submissions/complete?cc=${encodeURIComponent(completionCode)}`;
  }

  function getExperimentMode() {
    const params = new URLSearchParams(window.location.search);
    const debugValue = (params.get("debug") || "").toLowerCase();
    const modeValue = (params.get("mode") || "").toLowerCase();
    const isDebug = ["1", "true", "yes"].includes(debugValue) || modeValue === "debug";

    return {
      isDebug,
      mode: isDebug ? "debug" : "full",
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
      target_speaker: params.get("TAR_SPK") || "",
      source: prolificPid ? "prolific" : "local_or_direct",
    };
  }

  function resolveAudioSpeaker(info, config) {
    const allowedProlificIds = Array.isArray(config.prolific_audio_speaker_ids)
      ? config.prolific_audio_speaker_ids
      : [];

    if (info.prolific_pid && allowedProlificIds.includes(info.prolific_pid)) {
      return { id: info.prolific_pid, source: "PROLIFIC_PID" };
    }
    if (info.target_speaker) {
      return { id: info.target_speaker, source: "TAR_SPK" };
    }
    if (!info.prolific_pid && config.preview_audio_speaker_id) {
      return {
        id: config.preview_audio_speaker_id,
        source: isQuestionPreview ? "preview_fallback" : "local_fallback",
      };
    }

    throw new Error(
      "TAR_SPK is required when PROLIFIC_PID is not in experiment_config.prolific_audio_speaker_ids."
    );
  }

  function isApprovedProlificParticipant(prolificPid, config) {
    const allowedProlificIds = Array.isArray(config.prolific_audio_speaker_ids)
      ? config.prolific_audio_speaker_ids
      : [];
    return Boolean(prolificPid) && allowedProlificIds.includes(prolificPid);
  }

  function sanitiseFilename(value) {
    return String(value || "participant").replace(/[^A-Za-z0-9_-]/g, "_");
  }

  function shuffleCopy(items) {
    const shuffled = [...items];
    for (let index = shuffled.length - 1; index > 0; index -= 1) {
      const randomIndex = Math.floor(Math.random() * (index + 1));
      [shuffled[index], shuffled[randomIndex]] = [shuffled[randomIndex], shuffled[index]];
    }
    return shuffled;
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function escapeAttribute(value) {
    return escapeHtml(value).replaceAll("`", "&#096;");
  }
})();
