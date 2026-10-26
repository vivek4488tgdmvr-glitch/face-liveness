"""
Runnable webcam demo of the passive -> active liveness flow.

Controls:
  q  - quit
  r  - reset / retry
"""

import time
import cv2

from liveness_engine import LivenessEngine, ChallengeType

CHALLENGE_PROMPTS = {
    ChallengeType.BLINK: "Please blink",
    ChallengeType.SMILE: "Please smile",
    ChallengeType.TURN_LEFT: "Please turn your head to the left",
    ChallengeType.TURN_RIGHT: "Please turn your head to the right",
}

CHALLENGE_WINDOW_SECONDS = 3.0
MAX_RETRIES = 3


def draw_banner(frame, text, color=(255, 255, 255)):
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 40), (30, 30, 30), -1)
    cv2.putText(frame, text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)


def main():
    """Run the local webcam demonstration; this is not a production verifier."""
    engine = LivenessEngine()
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        engine.close()
        raise RuntimeError("Could not open webcam. Check camera permission or try another camera index.")

    state = "PASSIVE"
    attempts = 0
    challenge = None
    challenge_frames = []
    challenge_start = None

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                print("Webcam frame unavailable; stopping demo.")
                break
            frame = cv2.flip(frame, 1)

            if state == "PASSIVE":
                result = engine.evaluate_passive(frame)
                if result.issue is not None:
                    draw_banner(frame, f"Issue: {result.issue.name}", (0, 0, 255))
                elif result.score >= engine.PASSIVE_SCORE_THRESHOLD and not result.pad_detected:
                    # This score is a heuristic, not a trained anti-spoofing model.
                    # Do not present it as proof of identity or production-grade PAD.
                    draw_banner(frame, f"Heuristic passed ({result.score:.2f}); confirming action...", (0, 180, 255))
                    challenge = engine.select_challenge(list(CHALLENGE_PROMPTS.keys()))
                    challenge_frames = []
                    challenge_start = time.time()
                    state = "ACTIVE"
                else:
                    challenge = engine.select_challenge(list(CHALLENGE_PROMPTS.keys()))
                    challenge_frames = []
                    challenge_start = time.time()
                    state = "ACTIVE"

            elif state == "ACTIVE":
                elapsed = time.time() - challenge_start
                remaining = max(0.0, CHALLENGE_WINDOW_SECONDS - elapsed)
                draw_banner(frame, f"{CHALLENGE_PROMPTS[challenge]} ({remaining:.1f}s)")
                challenge_frames.append(frame.copy())

                if elapsed >= CHALLENGE_WINDOW_SECONDS:
                    result = engine.evaluate_challenge(challenge_frames, challenge)
                    if result.success:
                        draw_banner(frame, "Challenge action detected (prototype only)", (0, 200, 0))
                        cv2.imshow("Liveness Demo", frame)
                        cv2.waitKey(1200)
                        break
                    attempts += 1
                    if attempts >= MAX_RETRIES:
                        draw_banner(frame, "Could not verify liveness. Please try again.", (0, 0, 255))
                        cv2.imshow("Liveness Demo", frame)
                        cv2.waitKey(1600)
                        break
                    # Re-check passive state and choose a fresh random challenge.
                    state = "PASSIVE"
                    challenge = None
                    challenge_frames = []

            cv2.imshow("Liveness Demo", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("r"):
                state, attempts = "PASSIVE", 0
                challenge, challenge_frames, challenge_start = None, [], None
    finally:
        cap.release()
        cv2.destroyAllWindows()
        engine.close()


if __name__ == "__main__":
    main()
