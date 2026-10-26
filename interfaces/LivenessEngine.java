package io.mosip.registration.liveness;

import java.util.List;

/**
 * Liveness/PAD processing interface.
 *
 * Implementations are swappable (e.g. a bundled default model vs. a
 * vendor-supplied SDK) as long as they honor this contract — this is what
 * lets the challenge set and PAD technology evolve without touching the
 * Orchestrator or the UI.
 */
public interface LivenessEngine {

    /** Passive check: no user action required. Called on the first frame(s). */
    PassiveResult evaluatePassive(FaceFrame frame);

    /** System (not the user) selects the next active challenge. */
    ChallengeType selectChallenge(List<ChallengeType> enabledTypes);

    /** Validates that the requested challenge was performed across this frame window. */
    ChallengeResult evaluateChallenge(List<FaceFrame> frameWindow, ChallengeType challenge);

    final class PassiveResult {
        public final double score;              // 0.0–1.0 confidence the face is live
        public final boolean padDetected;
        public final PresentationAttackType attackType; // null unless padDetected — audit only, never shown to user
        public final DetectionIssue issue;       // e.g. NO_FACE, MULTIPLE_FACES, POOR_QUALITY — null if none

        public PassiveResult(double score, boolean padDetected, PresentationAttackType attackType, DetectionIssue issue) {
            this.score = score;
            this.padDetected = padDetected;
            this.attackType = attackType;
            this.issue = issue;
        }
    }

    final class ChallengeResult {
        public final boolean success;
        public final long completionTimeMs;

        public ChallengeResult(boolean success, long completionTimeMs) {
            this.success = success;
            this.completionTimeMs = completionTimeMs;
        }
    }

    enum ChallengeType { BLINK, SMILE, TURN_LEFT, TURN_RIGHT, LOOK_UP, LOOK_DOWN }

    enum PresentationAttackType { PRINTED_PHOTO, SCREEN_REPLAY, VIDEO_REPLAY, MASK, UNKNOWN }

    enum DetectionIssue { NO_FACE_DETECTED, MULTIPLE_FACES_DETECTED, POOR_FACE_QUALITY, INVALID_FRAME }
}
