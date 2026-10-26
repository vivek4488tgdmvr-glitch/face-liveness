package io.mosip.registration.liveness;

import java.util.List;
import io.mosip.registration.liveness.LivenessEngine.ChallengeType;

/**
 * Per-workflow liveness configuration. One instance per workflow
 * (RESIDENT_REGISTRATION, OPERATOR_AUTH, SUPERVISOR_AUTH) so each can be
 * tuned independently, as the spec requires.
 */
public final class LivenessConfig {

    public enum Workflow { RESIDENT_REGISTRATION, OPERATOR_AUTH, SUPERVISOR_AUTH }

    public final Workflow workflow;
    public final boolean livenessEnabled;
    public final boolean activeLivenessEnabled;
    public final double passiveThreshold;          // 0.0–1.0
    public final List<ChallengeType> enabledChallengeTypes;
    public final int minChallengeCount;
    public final long challengeTimeoutMs;
    public final int maxRetryCount;
    public final FailureBehavior onRepeatedFailure;

    public LivenessConfig(Workflow workflow, boolean livenessEnabled, boolean activeLivenessEnabled,
                           double passiveThreshold, List<ChallengeType> enabledChallengeTypes,
                           int minChallengeCount, long challengeTimeoutMs, int maxRetryCount,
                           FailureBehavior onRepeatedFailure) {
        this.workflow = workflow;
        this.livenessEnabled = livenessEnabled;
        this.activeLivenessEnabled = activeLivenessEnabled;
        this.passiveThreshold = passiveThreshold;
        this.enabledChallengeTypes = enabledChallengeTypes;
        this.minChallengeCount = minChallengeCount;
        this.challengeTimeoutMs = challengeTimeoutMs;
        this.maxRetryCount = maxRetryCount;
        this.onRepeatedFailure = onRepeatedFailure;
    }

    public enum FailureBehavior { BLOCK_AND_LOG, ESCALATE_TO_SUPERVISOR, ALLOW_MANUAL_OVERRIDE }
}
