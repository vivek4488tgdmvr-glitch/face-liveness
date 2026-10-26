package io.mosip.registration.liveness;

import java.util.ArrayList;
import java.util.List;
import io.mosip.registration.liveness.LivenessEngine.*;

/**
 * The single state machine reused by resident registration, operator auth,
 * and supervisor auth. Each caller supplies its own LivenessConfig
 * (workflow-specific policy) but the flow itself never changes — this is
 * what keeps the three integration points consistent, as the spec requires.
 */
public class LivenessOrchestrator {

    public interface UICallback {
        void onCheckingLiveness();                          // "Checking face liveness..."
        void onChallengePrompt(ChallengeType challenge);     // "Please blink" / "Please turn your head left"
        void onChallengeFeedback(String message);            // "Please continue", "Action detected", "Hold still"
        void onAccepted();
        void onRetry(int attemptsRemaining);
        void onRejected(String genericMessage);              // never expose PAD attack type to the UI
        void onDeviceIssue(FaceFrameSource.DeviceException error);
    }

    private final LivenessEngine engine;
    private final LivenessConfig config;
    private final AuditLogger audit;
    private final UICallback ui;

    private int attemptsUsed = 0;

    public LivenessOrchestrator(LivenessEngine engine, LivenessConfig config, AuditLogger audit, UICallback ui) {
        this.engine = engine;
        this.config = config;
        this.audit = audit;
        this.ui = ui;
    }

    /** Entry point: call with the first frame(s) captured from the device. */
    public void submitInitialFrame(FaceFrame frame) {
        if (!config.livenessEnabled) {
            ui.onAccepted(); // liveness disabled by config — pass straight through
            return;
        }

        ui.onCheckingLiveness();
        PassiveResult result = engine.evaluatePassive(frame);

        if (result.issue != null) {
            audit.log(config.workflow, "PASSIVE_ISSUE", result.issue.name());
            retryOrReject();
            return;
        }

        if (result.score >= config.passiveThreshold && !result.padDetected) {
            audit.log(config.workflow, "PASSIVE_ACCEPT", "score=" + result.score);
            ui.onAccepted();
            return;
        }

        if (result.padDetected) {
            audit.log(config.workflow, "PAD_DETECTED", String.valueOf(result.attackType));
        }

        if (!config.activeLivenessEnabled) {
            retryOrReject();
            return;
        }

        beginActiveChallenge();
    }

    private void beginActiveChallenge() {
        ChallengeType challenge = engine.selectChallenge(config.enabledChallengeTypes);
        ui.onChallengePrompt(challenge);
        // Caller streams subsequent frames into submitChallengeFrames() within config.challengeTimeoutMs
    }

    /** Called by the capture loop with the frame window collected after the prompt. */
    public void submitChallengeFrames(List<FaceFrame> frameWindow, ChallengeType challenge) {
        ChallengeResult result = engine.evaluateChallenge(frameWindow, challenge);
        audit.log(config.workflow, "ACTIVE_CHALLENGE", challenge + " success=" + result.success);

        if (result.success) {
            ui.onAccepted();
        } else {
            retryOrReject();
        }
    }

    private void retryOrReject() {
        attemptsUsed++;
        int remaining = config.maxRetryCount - attemptsUsed;

        if (remaining > 0) {
            ui.onRetry(remaining);
            beginActiveChallenge(); // new random challenge each retry
        } else {
            audit.log(config.workflow, "MAX_RETRIES_EXCEEDED", "attempts=" + attemptsUsed);
            ui.onRejected("We could not verify face liveness. Please try again.");
        }
    }

    public interface AuditLogger {
        void log(LivenessConfig.Workflow workflow, String event, String detail);
    }
}
