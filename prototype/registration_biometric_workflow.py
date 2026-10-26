"""
Registration + biometric-authorisation workflow scaffold for the MOSIP face-liveness prototype.

IMPORTANT:
- Research/demo scaffold only; not production biometric authentication.
- Does NOT store face images, face embeddings, fingerprints, or other biometric templates.
- Wire evaluate_liveness() to the server-side liveness engine.
- Wire verify_identity() to a separately validated biometric identity matcher.
- Never trust a liveness result sent by the browser as proof; calculate it server-side.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from flask import Blueprint, current_app, jsonify, request

workflow_bp = Blueprint("biometric_workflow", __name__)

DB_PATH = Path(os.environ.get("BIOMETRIC_WORKFLOW_DB", "instance/biometric_workflow.db"))


@dataclass
class LivenessDecision:
    # The engine should return a result in this server-side shape.
    passed: bool
    score: float | None = None
    reasons: list[str] | None = None


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_workflow_db() -> None:
    """Call once during app startup."""
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registration_sessions (
                session_id TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL,
                consent_given INTEGER NOT NULL CHECK (consent_given IN (0, 1)),
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registration_records (
                subject_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                registered_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS authorisation_attempts (
                attempt_id TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL,
                outcome TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )


def _json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def _get_callbacks():
    """
    Configure these callbacks in your Flask app before registering the blueprint:
      app.config["EVALUATE_LIVENESS"] = your_server_side_liveness_function
      app.config["VERIFY_IDENTITY"] = your_identity_match_function

    EVALUATE_LIVENESS(payload) -> dict with:
      {"passed": bool, "score": optional float, "reasons": optional list[str]}

    VERIFY_IDENTITY(subject_id, payload) -> bool
      This must compare against an enrolled template using a validated matcher.
      This scaffold intentionally does not implement face recognition.
    """
    return (
        current_app.config.get("EVALUATE_LIVENESS"),
        current_app.config.get("VERIFY_IDENTITY"),
    )


def _evaluate_liveness(payload: dict[str, Any]) -> LivenessDecision:
    evaluate, _ = _get_callbacks()
    if not callable(evaluate):
        raise RuntimeError(
            "Server-side liveness callback is not configured. "
            "Set app.config['EVALUATE_LIVENESS']."
        )
    result = evaluate(payload)
    if not isinstance(result, dict) or not isinstance(result.get("passed"), bool):
        raise RuntimeError("Liveness callback must return {'passed': bool, ...}.")
    score = result.get("score")
    if score is not None:
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = None
    reasons = result.get("reasons", [])
    if not isinstance(reasons, list):
        reasons = []
    return LivenessDecision(result["passed"], score, [str(x)[:200] for x in reasons[:10]])


@workflow_bp.post("/api/registration/start")
def registration_start():
    """
    Start a demo registration session.
    JSON: {"subject_id": "demo-user-001", "consent": true}
    The subject_id should be an application-issued opaque identifier, not a national ID.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _json_error("Send a JSON object.")

    subject_id = data.get("subject_id")
    consent = data.get("consent")
    if not isinstance(subject_id, str) or not subject_id.strip() or len(subject_id) > 100:
        return _json_error("subject_id must be a non-empty string (max 100 characters).")
    if consent is not True:
        return _json_error("Explicit consent is required to start registration.", 403)

    now = int(time.time())
    session_id = secrets.token_urlsafe(24)
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO registration_sessions
                (session_id, subject_id, consent_given, status, created_at, expires_at)
            VALUES (?, ?, 1, 'pending_liveness', ?, ?)
            """,
            (session_id, subject_id.strip(), now, now + 10 * 60),
        )

    return jsonify({
        "ok": True,
        "session_id": session_id,
        "status": "pending_liveness",
        "expires_in_seconds": 600,
        "message": "Capture a fresh sample and submit it to the server-side liveness check.",
    }), 201


@workflow_bp.post("/api/registration/<session_id>/complete")
def registration_complete(session_id: str):
    """
    Complete the registration workflow only after server-side liveness passes.
    JSON payload should contain the sample/frames expected by your liveness engine.
    Do not send a client-provided {"passed": true} field and trust it.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _json_error("Send a JSON object containing the capture payload.")

    now = int(time.time())
    with _db() as conn:
        session = conn.execute(
            "SELECT * FROM registration_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()

    if session is None:
        return _json_error("Registration session not found.", 404)
    if session["expires_at"] < now:
        return _json_error("Registration session expired. Start again.", 410)
    if not session["consent_given"]:
        return _json_error("Consent is missing.", 403)
    if session["status"] != "pending_liveness":
        return _json_error("Session is not awaiting liveness.", 409)

    try:
        decision = _evaluate_liveness(payload)
    except RuntimeError as exc:
        current_app.logger.exception("Liveness callback is not ready")
        return _json_error(str(exc), 503)

    if not decision.passed:
        with _db() as conn:
            conn.execute(
                "UPDATE registration_sessions SET status = 'liveness_failed' WHERE session_id = ?",
                (session_id,),
            )
        return jsonify({
            "ok": False,
            "status": "liveness_failed",
            "registered": False,
            "reason": "The liveness check did not pass. Retry with a fresh capture or follow the manual review process.",
            "signals": decision.reasons or [],
        }), 422

    with _db() as conn:
        conn.execute(
            "UPDATE registration_sessions SET status = 'completed' WHERE session_id = ?",
            (session_id,),
        )
        conn.execute(
            """
            INSERT INTO registration_records (subject_id, status, registered_at)
            VALUES (?, 'liveness_passed_pending_identity_enrolment', ?)
            ON CONFLICT(subject_id) DO UPDATE SET
                status = excluded.status,
                registered_at = excluded.registered_at
            """,
            (session["subject_id"], now),
        )

    return jsonify({
        "ok": True,
        "status": "liveness_passed_pending_identity_enrolment",
        "registered": False,
        "subject_id": session["subject_id"],
        "message": (
            "Liveness passed. This prototype does not enrol a biometric template; "
            "complete identity enrolment through a separately validated, consented module."
        ),
        "signals": decision.reasons or [],
    }), 200


@workflow_bp.post("/api/biometric/authorize")
def biometric_authorize():
    """
    Liveness-gated authorisation attempt.
    JSON: {"subject_id": "demo-user-001", ...capture payload...}
    A separate identity matcher must confirm the claimed subject.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _json_error("Send a JSON object.")

    subject_id = data.get("subject_id")
    if not isinstance(subject_id, str) or not subject_id.strip() or len(subject_id) > 100:
        return _json_error("subject_id must be a non-empty string (max 100 characters).")

    with _db() as conn:
        registration = conn.execute(
            "SELECT status FROM registration_records WHERE subject_id = ?",
            (subject_id.strip(),),
        ).fetchone()

    attempt_id = secrets.token_urlsafe(12)
    now = int(time.time())

    def record(outcome: str, reason: str):
        with _db() as conn:
            conn.execute(
                """
                INSERT INTO authorisation_attempts
                    (attempt_id, subject_id, outcome, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (attempt_id, subject_id.strip(), outcome, reason[:250], now),
            )

    if registration is None:
        record("denied", "subject_not_registered")
        return jsonify({
            "ok": True, "authorised": False, "status": "denied",
            "reason": "subject_not_registered", "attempt_id": attempt_id,
        }), 403

    if registration["status"] != "liveness_passed_pending_identity_enrolment":
        record("denied", "registration_not_ready")
        return jsonify({
            "ok": True, "authorised": False, "status": "denied",
            "reason": "registration_not_ready", "attempt_id": attempt_id,
        }), 403

    try:
        decision = _evaluate_liveness(data)
    except RuntimeError as exc:
        current_app.logger.exception("Liveness callback is not ready")
        return _json_error(str(exc), 503)

    if not decision.passed:
        record("denied", "liveness_failed")
        return jsonify({
            "ok": True, "authorised": False, "status": "denied",
            "reason": "liveness_failed", "signals": decision.reasons or [],
            "attempt_id": attempt_id,
        }), 403

    _, verify_identity = _get_callbacks()
    if not callable(verify_identity):
        record("not_evaluated", "identity_matcher_not_configured")
        return jsonify({
            "ok": False,
            "authorised": False,
            "status": "identity_verification_required",
            "reason": (
                "Liveness passed, but no validated identity matcher is configured. "
                "No authorisation is granted."
            ),
            "attempt_id": attempt_id,
            "signals": decision.reasons or [],
        }), 501

    try:
        identity_matches = verify_identity(subject_id.strip(), data)
    except Exception:
        current_app.logger.exception("Identity verification callback failed")
        record("not_evaluated", "identity_verification_error")
        return _json_error("Identity verification failed safely; no authorisation granted.", 503)

    if identity_matches is not True:
        record("denied", "identity_mismatch")
        return jsonify({
            "ok": True, "authorised": False, "status": "denied",
            "reason": "identity_mismatch", "attempt_id": attempt_id,
            "signals": decision.reasons or [],
        }), 403

    # This means the configured liveness + identity checks passed. A real
    # deployment still needs its own policy/permission check before granting access.
    record("checks_passed_pending_policy", "liveness_and_identity_passed")
    return jsonify({
        "ok": True,
        "authorised": False,
        "status": "checks_passed_pending_policy",
        "reason": (
            "Liveness and identity checks passed. Application policy/permission "
            "checks are still required; this endpoint does not grant access."
        ),
        "attempt_id": attempt_id,
        "signals": decision.reasons or [],
    }), 200


@workflow_bp.get("/api/registration/status/<subject_id>")
def registration_status(subject_id: str):
    """Return a minimal status only. Add authentication/authorisation in real deployments."""
    if not subject_id or len(subject_id) > 100:
        return _json_error("Invalid subject_id.")
    with _db() as conn:
        row = conn.execute(
            "SELECT status, registered_at FROM registration_records WHERE subject_id = ?",
            (subject_id,),
        ).fetchone()
    if row is None:
        return jsonify({"ok": True, "found": False, "status": "not_registered"})
    return jsonify({
        "ok": True,
        "found": True,
        "status": row["status"],
        "registered_at": row["registered_at"],
    })


def register_biometric_workflow(app) -> None:
    """Call from prototype/api.py after creating the Flask app."""
    init_workflow_db()
    app.register_blueprint(workflow_bp)
