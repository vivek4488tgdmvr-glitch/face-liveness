package io.mosip.registration.liveness;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import io.mosip.registration.liveness.LivenessEngine.ChallengeType;

/**
 * Accessibility-adaptive challenge policy.
 *
 * MOSIP's Registration Client is used to enroll entire populations,
 * including elderly residents with limited neck mobility or tremor,
 * residents with facial paralysis or motor impairments who cannot
 * reliably perform some active challenges, and low-literacy residents
 * who cannot read a text prompt. A rigid, one-size-fits-all challenge
 * flow silently discriminates against exactly the people national ID
 * systems most need to reach.
 *
 * This policy does two things the base spec leaves open:
 *   1. If a given challenge type fails repeatedly for a resident, fall
 *      back to an easier alternative from a different motion family
 *      rather than just repeating (or blocking) the same ask.
 *   2. Support non-text prompt delivery (icon / audio) so the UI layer
 *      can serve low-literacy or visually-impaired residents.
 *
 * This never weakens PAD -- the underlying liveness/PAD evaluation is
 * unchanged. It only changes *which* legitimate challenge is asked of
 * *this* resident, and *how* it's communicated.
 */
public final class AccessibilityChallengePolicy {

    public enum PromptMode { TEXT, ICON, AUDIO }

    // Each challenge maps to a fallback from a different motion family,
    // so a resident who structurally can't do one still has a real option.
    private static final Map<ChallengeType, ChallengeType> FALLBACKS = new HashMap<>();
    static {
        FALLBACKS.put(ChallengeType.TURN_LEFT, ChallengeType.BLINK);
        FALLBACKS.put(ChallengeType.TURN_RIGHT, ChallengeType.BLINK);
        FALLBACKS.put(ChallengeType.LOOK_UP, ChallengeType.SMILE);
        FALLBACKS.put(ChallengeType.LOOK_DOWN, ChallengeType.SMILE);
        FALLBACKS.put(ChallengeType.BLINK, ChallengeType.SMILE);
        FALLBACKS.put(ChallengeType.SMILE, ChallengeType.BLINK);
    }

    private final Map<ChallengeType, Integer> failureCounts = new HashMap<>();
    private final int fallbackAfterFailures;
    private final PromptMode promptMode;

    public AccessibilityChallengePolicy(int fallbackAfterFailures, PromptMode promptMode) {
        this.fallbackAfterFailures = fallbackAfterFailures;
        this.promptMode = promptMode;
    }

    /** Call after each failed challenge attempt. */
    public void recordFailure(ChallengeType challenge) {
        failureCounts.merge(challenge, 1, Integer::sum);
    }

    public void reset() {
        failureCounts.clear();
    }

    /**
     * Given the config-enabled pool and the last-attempted challenge,
     * return the pool the orchestrator should actually draw the next
     * random challenge from -- swapping in a fallback if the resident
     * has struggled with the same motion family too many times.
     */
    public List<ChallengeType> adjustedPool(List<ChallengeType> enabledTypes, ChallengeType lastAttempted) {
        int failures = failureCounts.getOrDefault(lastAttempted, 0);
        if (failures < fallbackAfterFailures) {
            return enabledTypes;
        }

        ChallengeType fallback = FALLBACKS.get(lastAttempted);
        if (fallback == null || !enabledTypes.contains(fallback)) {
            return enabledTypes; // no safe fallback configured -- don't narrow the pool to nothing
        }

        List<ChallengeType> adjusted = new ArrayList<>();
        adjusted.add(fallback);
        return adjusted;
    }

    /** UI-facing prompt text/asset key, keyed by mode -- lets the client swap in
     *  an icon or an audio clip instead of English text for low-literacy residents. */
    public String promptKeyFor(ChallengeType challenge) {
        // e.g. "challenge.blink.icon", "challenge.blink.audio.hi", "challenge.blink.text"
        return "challenge." + challenge.name().toLowerCase() + "." + promptMode.name().toLowerCase();
    }

    public PromptMode getPromptMode() {
        return promptMode;
    }
}
