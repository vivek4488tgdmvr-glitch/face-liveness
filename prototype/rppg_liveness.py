"""
Remote photoplethysmography (rPPG) as a second, independent passive
liveness signal.

Idea: a live human's facial skin shows tiny, periodic color changes in
sync with their heartbeat (invisible to the eye, extractable from video).
A printed photo, a mask, or most screen-replay setups do not reproduce
this physiological signal convincingly. Fusing this with the
texture/frequency PAD score in liveness_engine.py gives two
*independent* lines of evidence an attacker has to defeat simultaneously
-- which is a materially harder bar than a single CNN score, and it's a
signal almost no other hackathon submission on this problem will include.

Method: track the forehead ROI across a short window of frames, average
the green channel (most sensitive to blood-volume changes), detrend and
bandpass-filter to the physiological heart-rate band (0.7-4 Hz / 42-240
bpm), then look for a clear dominant frequency peak via FFT. A strong,
plausible peak => real pulse => higher liveness confidence. A flat or
noisy spectrum => treat as inconclusive, not as an automatic reject (to
avoid penalizing genuinely still/calm subjects or poor lighting).
"""

from dataclasses import dataclass
from typing import List

import cv2
import numpy as np

FOREHEAD_LANDMARKS = [10, 338, 297, 332, 284, 251, 21, 54, 103, 67, 109]  # mediapipe face mesh forehead band


@dataclass
class RppgResult:
    confidence: float          # 0.0-1.0, contribution to fused passive score
    estimated_bpm: float       # for diagnostics/audit log only
    signal_quality: float      # 0.0-1.0, how trustworthy the estimate is


def _forehead_roi(frame, landmarks, w, h):
    pts = np.array([[landmarks[i].x * w, landmarks[i].y * h] for i in FOREHEAD_LANDMARKS], dtype=np.int32)
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    cv2.fillConvexPoly(mask, cv2.convexHull(pts), 255)
    return mask


def estimate_rppg(frames: List[np.ndarray], landmarks_per_frame, fps: float = 15.0) -> RppgResult:
    """
    frames: list of BGR frames spanning ~3-5 seconds
    landmarks_per_frame: matching list of mediapipe face landmarks (or None for a dropped frame)
    """
    green_means = []
    for frame, lm in zip(frames, landmarks_per_frame):
        if lm is None:
            continue
        h, w = frame.shape[:2]
        mask = _forehead_roi(frame, lm, w, h)
        green_channel = frame[:, :, 1]
        region = green_channel[mask > 0]
        if region.size == 0:
            continue
        green_means.append(float(region.mean()))

    if len(green_means) < int(fps * 2):  # need at least ~2s of signal to say anything meaningful
        return RppgResult(confidence=0.5, estimated_bpm=0.0, signal_quality=0.0)  # inconclusive, not penalized

    signal = np.array(green_means)
    signal = signal - np.mean(signal)  # detrend (DC removal)

    # Bandpass to plausible heart-rate range via FFT masking
    freqs = np.fft.rfftfreq(len(signal), d=1.0 / fps)
    spectrum = np.abs(np.fft.rfft(signal))

    band = (freqs >= 0.7) & (freqs <= 4.0)
    if not np.any(band):
        return RppgResult(confidence=0.5, estimated_bpm=0.0, signal_quality=0.0)

    band_freqs = freqs[band]
    band_spectrum = spectrum[band]

    peak_idx = int(np.argmax(band_spectrum))
    peak_freq = band_freqs[peak_idx]
    peak_power = band_spectrum[peak_idx]
    total_power = band_spectrum.sum() + 1e-8
    peak_prominence = peak_power / total_power  # how dominant is this one frequency vs. noise

    estimated_bpm = float(peak_freq * 60.0)
    signal_quality = float(np.clip(peak_prominence * 3.0, 0.0, 1.0))  # tune against labeled data

    # Confidence: strong, physiologically-plausible peak -> high confidence of liveness.
    # A completely flat/noisy spectrum stays neutral (0.5) rather than penalizing --
    # bad lighting or a very still subject shouldn't tank the score on its own.
    plausible_bpm = 40 <= estimated_bpm <= 180
    confidence = 0.5 + 0.5 * signal_quality if plausible_bpm else 0.5

    return RppgResult(confidence=confidence, estimated_bpm=estimated_bpm, signal_quality=signal_quality)


def fuse_scores(texture_freq_score: float, rppg: RppgResult, rppg_weight: float = 0.35) -> float:
    """Combine the existing texture/frequency PAD score with the rPPG signal.
    rppg_weight is intentionally modest -- rPPG is a corroborating signal,
    not a replacement for the primary PAD model."""
    return float(np.clip((1 - rppg_weight) * texture_freq_score + rppg_weight * rppg.confidence, 0.0, 1.0))
