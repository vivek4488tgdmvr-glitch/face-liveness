"""Local Flask API for the MOSIP Face Liveness research prototype.

This is a development/demo server, not a production identity-verification service.
It accepts one JPEG frame at a time and returns heuristic diagnostics only.
"""
from __future__ import annotations

import os
import threading

import cv2
import numpy as np
from flask import Flask, jsonify, request, send_from_directory
from liveness_engine import LivenessEngine, DetectionIssue

app = Flask(__name__)
@app.get("/")
def home():
    return send_from_directory(
        str(app.root_path + "/.."),
        "index.html"
    )


app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MiB request limit

_engine = None
_engine_lock = threading.Lock()
MAX_IMAGE_WIDTH = 1280
MAX_IMAGE_HEIGHT = 1280


def get_engine():
    global _engine
    if _engine is None:
        _engine = LivenessEngine()
    return _engine


@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "service": "mosip-face-liveness-prototype",
        "mode": "research-heuristic",
        "model_trained": False,
    })


@app.post("/api/analyze")
def analyze():
    if not request.is_json:
        return jsonify({"ok": False, "error": "Expected JSON with a base64-free JPEG data URL in 'image'."}), 415

    payload = request.get_json(silent=True) or {}
    image_value = payload.get("image")
    if not isinstance(image_value, str) or not image_value.startswith("data:image/jpeg;base64,"):
        return jsonify({"ok": False, "error": "Expected a JPEG data URL."}), 400

    import base64
    import binascii

    encoded = image_value.split(",", 1)[1]
    if len(encoded) > 1_500_000:
        return jsonify({"ok": False, "error": "Image is too large. Send a smaller frame."}), 413
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return jsonify({"ok": False, "error": "Invalid base64 image data."}), 400

    if not raw or len(raw) > 1_100_000:
        return jsonify({"ok": False, "error": "Image is empty or exceeds the frame limit."}), 413

    frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify({"ok": False, "error": "Could not decode the image."}), 400

    height, width = frame.shape[:2]
    if width < 32 or height < 32:
        return jsonify({"ok": False, "error": "Frame is too small to analyze."}), 400
    if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
        scale = min(MAX_IMAGE_WIDTH / width, MAX_IMAGE_HEIGHT / height)
        frame = cv2.resize(frame, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)

    try:
        # MediaPipe FaceMesh is stateful; serialize calls to its shared instance.
        with _engine_lock:
            result = get_engine().evaluate_passive(frame)
    except Exception:
        app.logger.exception("Frame analysis failed")
        return jsonify({"ok": False, "error": "Frame analysis failed. Check server logs."}), 500

    issue = result.issue.name if result.issue else None
    if issue == DetectionIssue.NO_FACE_DETECTED.name:
        message = "No face detected. Adjust framing and lighting."
        state = "NO_FACE"
    elif issue == DetectionIssue.MULTIPLE_FACES_DETECTED.name:
        message = "Multiple faces detected. Use a single-face frame."
        state = "MULTIPLE_FACES"
    elif issue == DetectionIssue.POOR_FACE_QUALITY.name:
        message = "Face or image quality is insufficient."
        state = "POOR_QUALITY"
    elif result.pad_detected:
        message = "Heuristic flagged this frame for review; this is not a verified spoof finding."
        state = "REVIEW"
    else:
        message = "Frame passed the heuristic threshold only; this is not proof of liveness."
        state = "HEURISTIC_PASS"

    return jsonify({
        "ok": True,
        "state": state,
        "message": message,
        "score": round(float(result.score), 4),
        "issue": issue,
        "model_trained": False,
        "warning": "Experimental texture heuristic; not validated for production anti-spoofing.",
    })


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"ok": False, "error": "Request exceeds the 2 MiB limit."}), 413




@app.get("/<path:filename>")
def static_files(filename):
    # Serve only project-root files; do not expose parent directories.
    return send_from_directory(str(app.root_path + "/.."), filename)


def shutdown_engine():
    global _engine
    if _engine is not None:
        _engine.close()
        _engine = None


if __name__ == "__main__":
    # Run from the repository root. No external network interface by default.
    try:
        app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
    finally:
        shutdown_engine()
