"""
Reference prototype for the MOSIP Decode 2026 face liveness / PAD module.

This mirrors the Java interfaces in ../interfaces/ so the design can be
demoed quickly on a laptop webcam before porting into the actual Desktop
(Java) / Android Registration Client. It is NOT production PAD — the
passive score here is a texture/frequency heuristic standing in for a
trained anti-spoofing CNN (see README for the swap-in plan).

Run: python demo.py
"""

import random
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional

import cv2
import numpy as np
import mediapipe as mp


class ChallengeType(Enum):
    BLINK = auto()
    SMILE = auto()
    TURN_LEFT = auto()
    TURN_RIGHT = auto()


class DetectionIssue(Enum):
    NO_FACE_DETECTED = auto()
    MULTIPLE_FACES_DETECTED = auto()
    POOR_FACE_QUALITY = auto()


@dataclass
class PassiveResult:
    score: float
    pad_detected: bool
    issue: Optional[DetectionIssue] = None


@dataclass
class ChallengeResult:
    success: bool
    completion_time_ms: float


# Mediapipe landmark indices used for the heuristics below
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]
MOUTH_CORNERS = [61, 291]
MOUTH_TOP_BOTTOM = [13, 14]
NOSE_TIP = 1
LEFT_CHEEK = 234
RIGHT_CHEEK = 454


def _eye_aspect_ratio(landmarks, eye_idx, w, h):
    pts = np.array([[landmarks[i].x * w, landmarks[i].y * h] for i in eye_idx])
    vert1 = np.linalg.norm(pts[1] - pts[5])
    vert2 = np.linalg.norm(pts[2] - pts[4])
    horiz = np.linalg.norm(pts[0] - pts[3])
    return (vert1 + vert2) / (2.0 * horiz)


def _mouth_ratio(landmarks, w, h):
    left, right = [landmarks[i] for i in MOUTH_CORNERS]
    top, bottom = [landmarks[i] for i in MOUTH_TOP_BOTTOM]
    width = np.hypot((right.x - left.x) * w, (right.y - left.y) * h)
    height = np.hypot((bottom.x - top.x) * w, (bottom.y - top.y) * h)
    return height / width


def _yaw_ratio(landmarks, w, h):
    """Rough left/right head-turn proxy: nose position relative to cheeks."""
    nose = landmarks[NOSE_TIP]
    left_cheek = landmarks[LEFT_CHEEK]
    right_cheek = landmarks[RIGHT_CHEEK]
    nose_x = nose.x * w
    left_x = left_cheek.x * w
    right_x = right_cheek.x * w
    total = right_x - left_x
    if total == 0:
        return 0.0
    return ((nose_x - left_x) / total) - 0.5  # ~0 = facing camera, negative/positive = turned


class LivenessEngine:
    """Passive + active liveness engine. Mirrors LivenessEngine.java."""

    BLINK_EAR_THRESHOLD = 0.21
    SMILE_RATIO_THRESHOLD = 0.55
    YAW_TURN_THRESHOLD = 0.18
    PASSIVE_SCORE_THRESHOLD = 0.6

    def __init__(self):
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=2,  # detect 2 so we can flag MULTIPLE_FACES_DETECTED
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def close(self):
        """Release MediaPipe resources. Safe to call during error cleanup."""
        face_mesh = getattr(self, "face_mesh", None)
        if face_mesh is not None:
            face_mesh.close()
            self.face_mesh = None

    def evaluate_passive(self, frame) -> PassiveResult:
        if frame is None or getattr(frame, "ndim", 0) != 3 or frame.shape[2] != 3:
            return PassiveResult(score=0.0, pad_detected=False, issue=DetectionIssue.POOR_FACE_QUALITY)
        h, w = frame.shape[:2]
        if h < 2 or w < 2:
            return PassiveResult(score=0.0, pad_detected=False, issue=DetectionIssue.POOR_FACE_QUALITY)
        results = self.face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        if not results.multi_face_landmarks:
            return PassiveResult(score=0.0, pad_detected=False, issue=DetectionIssue.NO_FACE_DETECTED)
        if len(results.multi_face_landmarks) > 1:
            return PassiveResult(score=0.0, pad_detected=False, issue=DetectionIssue.MULTIPLE_FACES_DETECTED)

        # --- heuristic PAD proxy: texture sharpness + high-frequency energy ---
        # Real screens/printouts tend to show characteristic blur or moiré
        # patterns a trained CNN would catch; this stands in for that model.
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
        sharpness_score = min(sharpness / 500.0, 1.0)  # normalize, tune per camera

        fft = np.fft.fftshift(np.fft.fft2(gray))
        magnitude = np.log(np.abs(fft) + 1)
        high_freq_energy = magnitude[magnitude.shape[0] // 4:, magnitude.shape[1] // 4:].mean()
        freq_score = min(high_freq_energy / 10.0, 1.0)

        score = float(np.clip(0.5 * sharpness_score + 0.5 * freq_score, 0.0, 1.0))
        pad_detected = score < 0.25  # heuristic-only cutoff; tune against a labeled PAD dataset

        if sharpness_score < 0.15:
            return PassiveResult(score=score, pad_detected=pad_detected, issue=DetectionIssue.POOR_FACE_QUALITY)

        return PassiveResult(score=score, pad_detected=pad_detected)

    def select_challenge(self, enabled_types: List[ChallengeType]) -> ChallengeType:
        return random.choice(enabled_types)  # system picks — never the user

    def evaluate_challenge(self, frames, challenge: ChallengeType) -> ChallengeResult:
        start = time.time()
        if not frames:
            return ChallengeResult(success=False, completion_time_ms=0.0)
        h, w = frames[0].shape[:2]

        if challenge == ChallengeType.BLINK:
            success = self._detect_blink(frames, w, h)
        elif challenge == ChallengeType.SMILE:
            success = self._detect_smile(frames, w, h)
        elif challenge in (ChallengeType.TURN_LEFT, ChallengeType.TURN_RIGHT):
            success = self._detect_turn(frames, w, h, challenge)
        else:
            success = False

        return ChallengeResult(success=bool(success), completion_time_ms=(time.time() - start) * 1000)

    def _landmarks_for(self, frame):
        results = self.face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if not results.multi_face_landmarks:
            return None
        return results.multi_face_landmarks[0].landmark

    def _detect_blink(self, frames, w, h) -> bool:
        ears = []
        for frame in frames:
            lm = self._landmarks_for(frame)
            if lm is None:
                continue
            ear = (_eye_aspect_ratio(lm, LEFT_EYE, w, h) + _eye_aspect_ratio(lm, RIGHT_EYE, w, h)) / 2.0
            ears.append(ear)
        # A blink = EAR dips below threshold then recovers above it
        return any(e < self.BLINK_EAR_THRESHOLD for e in ears) and ears and ears[-1] >= self.BLINK_EAR_THRESHOLD

    def _detect_smile(self, frames, w, h) -> bool:
        for frame in frames:
            lm = self._landmarks_for(frame)
            if lm is None:
                continue
            if _mouth_ratio(lm, w, h) > self.SMILE_RATIO_THRESHOLD:
                return True
        return False

    def _detect_turn(self, frames, w, h, challenge: ChallengeType) -> bool:
        for frame in frames:
            lm = self._landmarks_for(frame)
            if lm is None:
                continue
            yaw = _yaw_ratio(lm, w, h)
            if challenge == ChallengeType.TURN_LEFT and yaw > self.YAW_TURN_THRESHOLD:
                return True
            if challenge == ChallengeType.TURN_RIGHT and yaw < -self.YAW_TURN_THRESHOLD:
                return True
        return False
