"""
Offline, session-scoped replay-presentation guard.

See docs/differentiators.md section 4 for the honest positioning of this
idea relative to existing prior art (US 9256720's "colluding operator"
problem statement, Entrust's "Known Faces & Repeat Attempt"). This module
adapts that established concept to run fully offline, on a single device,
fingerprinting non-biometric environmental signal rather than the face --
it is NOT an identity match and must never be treated as one.

Fingerprint components (all deliberately non-biometric):
  - Background micro-texture (region outside the face bounding box)
  - Coarse lighting gradient across the frame
  - Sensor noise signature (high-frequency residual after denoising)

These three together give a rough "is this the same physical setup being
re-shown" signal without ever touching the resident's face biometric.
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class PresentationFingerprint:
    background_hist: np.ndarray   # small color histogram of the non-face region
    lighting_gradient: np.ndarray  # coarse 4x4 brightness grid
    noise_signature: float         # scalar summary of high-frequency residual energy
    captured_at: float = field(default_factory=time.time)


@dataclass
class ReplayFlag:
    is_likely_replay: bool
    similarity: float          # 0.0-1.0, higher = more similar to a cached fingerprint
    matched_age_seconds: Optional[float]


class ReplayFingerprintGuard:
    """
    Session-scoped cache, local to one device. Not persisted long-term,
    not synced anywhere, not tied to identity -- purely an operational
    fraud signal for a supervisor to review.
    """

    def __init__(self, similarity_threshold: float = 0.9, window_seconds: float = 3600.0, max_cache: int = 200):
        self.similarity_threshold = similarity_threshold
        self.window_seconds = window_seconds
        self.max_cache = max_cache
        self._cache: List[PresentationFingerprint] = []

    def extract(self, frame: np.ndarray, face_bbox: Tuple[int, int, int, int]) -> PresentationFingerprint:
        h, w = frame.shape[:2]
        fx, fy, fw, fh = face_bbox

        mask = np.ones((h, w), dtype=np.uint8) * 255
        cv2.rectangle(mask, (fx, fy), (fx + fw, fy + fh), 0, -1)  # exclude the face region entirely

        background = cv2.bitwise_and(frame, frame, mask=mask)
        hist = cv2.calcHist([background], [0, 1, 2], mask, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        hist = cv2.normalize(hist, hist).flatten()

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        grid = cv2.resize(gray, (4, 4)).astype(np.float32) / 255.0  # coarse lighting gradient

        denoised = cv2.GaussianBlur(gray, (5, 5), 0)
        residual = gray.astype(np.float32) - denoised.astype(np.float32)
        noise_signature = float(np.std(residual))

        return PresentationFingerprint(background_hist=hist, lighting_gradient=grid, noise_signature=noise_signature)

    def _similarity(self, a: PresentationFingerprint, b: PresentationFingerprint) -> float:
        hist_sim = float(cv2.compareHist(a.background_hist, b.background_hist, cv2.HISTCMP_CORREL))
        hist_sim = max(0.0, hist_sim)  # correlation can be negative; clamp for scoring

        grid_diff = float(np.mean(np.abs(a.lighting_gradient - b.lighting_gradient)))
        grid_sim = max(0.0, 1.0 - grid_diff)

        noise_diff = abs(a.noise_signature - b.noise_signature)
        noise_sim = max(0.0, 1.0 - min(noise_diff / 10.0, 1.0))

        return 0.5 * hist_sim + 0.3 * grid_sim + 0.2 * noise_sim

    def check_and_register(self, fingerprint: PresentationFingerprint) -> ReplayFlag:
        """Call this once per ACCEPTED capture (i.e. after liveness/PAD already
        passed). Compares against the recent session cache, then registers
        this fingerprint for future comparisons."""
        now = time.time()
        self._cache = [fp for fp in self._cache if now - fp.captured_at <= self.window_seconds]

        best_similarity = 0.0
        best_age = None
        for cached in self._cache:
            sim = self._similarity(fingerprint, cached)
            if sim > best_similarity:
                best_similarity = sim
                best_age = now - cached.captured_at

        self._cache.append(fingerprint)
        if len(self._cache) > self.max_cache:
            self._cache.pop(0)

        return ReplayFlag(
            is_likely_replay=best_similarity >= self.similarity_threshold,
            similarity=best_similarity,
            matched_age_seconds=best_age,
        )
