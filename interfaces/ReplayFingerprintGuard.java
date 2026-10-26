package io.mosip.registration.liveness;

import java.util.ArrayDeque;
import java.util.Deque;

/**
 * Offline, session-scoped replay-presentation guard.
 *
 * See docs/differentiators.md section 4 for honest positioning against
 * prior art (colluding-operator fraud is a documented problem; repeat-
 * attempt detection exists in connected KYC products). This adapts the
 * same concept to run fully on-device with no connectivity, using
 * non-biometric environmental signal -- never the face itself -- so it
 * must never be wired into identity decisions. It is purely an
 * operational fraud signal surfaced to a supervisor.
 *
 * Call registerAndCheck() once per ACCEPTED capture (after liveness/PAD
 * has already passed), not on every frame.
 */
public final class ReplayFingerprintGuard {

    public static final class Fingerprint {
        public final double[] backgroundHistogram; // small color histogram, face region excluded
        public final double[] lightingGrid;         // coarse brightness grid
        public final double noiseSignature;         // high-frequency residual summary
        public final long capturedAtMillis;

        public Fingerprint(double[] backgroundHistogram, double[] lightingGrid, double noiseSignature, long capturedAtMillis) {
            this.backgroundHistogram = backgroundHistogram;
            this.lightingGrid = lightingGrid;
            this.noiseSignature = noiseSignature;
            this.capturedAtMillis = capturedAtMillis;
        }
    }

    public static final class ReplayFlag {
        public final boolean likelyReplay;
        public final double similarity;
        public final Long matchedAgeMillis; // null if no match

        public ReplayFlag(boolean likelyReplay, double similarity, Long matchedAgeMillis) {
            this.likelyReplay = likelyReplay;
            this.similarity = similarity;
            this.matchedAgeMillis = matchedAgeMillis;
        }
    }

    private final double similarityThreshold;
    private final long windowMillis;
    private final int maxCache;
    private final Deque<Fingerprint> cache = new ArrayDeque<>();

    public ReplayFingerprintGuard(double similarityThreshold, long windowMillis, int maxCache) {
        this.similarityThreshold = similarityThreshold;
        this.windowMillis = windowMillis;
        this.maxCache = maxCache;
    }

    public ReplayFlag registerAndCheck(Fingerprint fingerprint) {
        long now = fingerprint.capturedAtMillis;
        cache.removeIf(fp -> now - fp.capturedAtMillis > windowMillis);

        double bestSimilarity = 0.0;
        Long bestAge = null;
        for (Fingerprint cached : cache) {
            double sim = similarity(fingerprint, cached);
            if (sim > bestSimilarity) {
                bestSimilarity = sim;
                bestAge = now - cached.capturedAtMillis;
            }
        }

        cache.addLast(fingerprint);
        if (cache.size() > maxCache) {
            cache.removeFirst();
        }

        return new ReplayFlag(bestSimilarity >= similarityThreshold, bestSimilarity, bestAge);
    }

    private double similarity(Fingerprint a, Fingerprint b) {
        double histSim = Math.max(0.0, correlation(a.backgroundHistogram, b.backgroundHistogram));
        double gridDiff = meanAbsDiff(a.lightingGrid, b.lightingGrid);
        double gridSim = Math.max(0.0, 1.0 - gridDiff);
        double noiseDiff = Math.abs(a.noiseSignature - b.noiseSignature);
        double noiseSim = Math.max(0.0, 1.0 - Math.min(noiseDiff / 10.0, 1.0));
        return 0.5 * histSim + 0.3 * gridSim + 0.2 * noiseSim;
    }

    private double correlation(double[] a, double[] b) {
        double meanA = mean(a), meanB = mean(b);
        double num = 0, denA = 0, denB = 0;
        for (int i = 0; i < a.length; i++) {
            double da = a[i] - meanA, db = b[i] - meanB;
            num += da * db;
            denA += da * da;
            denB += db * db;
        }
        double denom = Math.sqrt(denA * denB);
        return denom == 0 ? 0.0 : num / denom;
    }

    private double meanAbsDiff(double[] a, double[] b) {
        double sum = 0;
        for (int i = 0; i < a.length; i++) sum += Math.abs(a[i] - b[i]);
        return sum / a.length;
    }

    private double mean(double[] a) {
        double sum = 0;
        for (double v : a) sum += v;
        return sum / a.length;
    }
}
