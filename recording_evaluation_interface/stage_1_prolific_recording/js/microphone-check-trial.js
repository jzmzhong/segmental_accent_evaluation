(function () {
  const info = {
    name: "microphone-check-trial",
    version: "0.1.0",
    parameters: {},
    data: {
      task: {
        type: jsPsychModule.ParameterType.STRING,
      },
      microphone_check_passed: {
        type: jsPsychModule.ParameterType.BOOL,
      },
      microphone_label: {
        type: jsPsychModule.ParameterType.STRING,
      },
    },
  };

  class MicrophoneCheckTrialPlugin {
    constructor(jsPsych) {
      this.jsPsych = jsPsych;
    }

    trial(displayElement) {
      let requestId = 0;

      displayElement.innerHTML = `
        <main class="page-panel">
          <h2>Microphone Check</h2>
          <p>Your browser will ask for microphone permission now. Choose Allow to continue.</p>
          <p>Recording works best on Chrome, Edge, Firefox, or Safari over HTTPS or localhost.</p>
          <div class="recording-controls">
            <button type="button" id="check-microphone">Allow microphone</button>
            <button type="button" id="continue" disabled>Continue</button>
          </div>
          <div class="recording-status" id="microphone-status" role="status">Microphone permission has not been checked yet.</div>
          <p class="permission-help" id="permission-help" hidden>
            If the permission window does not respond, press Escape, reload this page, and try again in Chrome, Edge, Firefox, or Safari.
          </p>
        </main>
      `;

      const checkButton = displayElement.querySelector("#check-microphone");
      const continueButton = displayElement.querySelector("#continue");
      const status = displayElement.querySelector("#microphone-status");
      const help = displayElement.querySelector("#permission-help");
      let microphoneLabel = "";

      const setStatus = (message, state = "") => {
        status.textContent = message;
        status.className = `recording-status ${state}`.trim();
      };

      checkButton.addEventListener("click", async () => {
        requestId += 1;
        const thisRequest = requestId;

        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          setStatus("This browser does not support microphone recording. Please try another browser.", "is-warning");
          help.hidden = false;
          return;
        }

        checkButton.disabled = true;
        help.hidden = true;
        setStatus("Requesting microphone access...");
        window.setTimeout(() => {
          if (thisRequest !== requestId || !continueButton.disabled) return;
          checkButton.disabled = false;
          help.hidden = false;
          setStatus("Microphone permission is still waiting for a browser response.", "is-warning");
        }, 12000);

        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          if (thisRequest !== requestId) {
            stream.getTracks().forEach((track) => track.stop());
            return;
          }
          const audioTrack = stream.getAudioTracks()[0];
          microphoneLabel = audioTrack ? audioTrack.label : "";
          stream.getTracks().forEach((track) => track.stop());

          continueButton.disabled = false;
          help.hidden = true;
          setStatus("Microphone access confirmed. You can continue to the recording task.");
        } catch (error) {
          if (thisRequest !== requestId) return;
          checkButton.disabled = false;
          continueButton.disabled = true;
          help.hidden = false;
          setStatus("Microphone access was blocked or unavailable. Please allow microphone access and try again.", "is-warning");
        }
      });

      continueButton.addEventListener("click", () => {
        this.jsPsych.finishTrial({
          task: "microphone_check",
          microphone_check_passed: true,
          microphone_label: microphoneLabel,
        });
      });
    }
  }

  window.MicrophoneCheckTrialPlugin = MicrophoneCheckTrialPlugin;
  window.MicrophoneCheckTrialPlugin.info = info;
})();
