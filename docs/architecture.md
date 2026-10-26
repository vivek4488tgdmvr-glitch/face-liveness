# Face Liveness & PAD Module — Architecture

## 1. Component overview

```mermaid
flowchart TD
    Device[L0/L1 Biometric Device] -->|frame stream| Adapter[Device Adapter Layer]
    Adapter --> Streamer[Face Frame Streamer]
    Streamer --> Engine[Liveness / PAD Engine]
    Engine -->|passive result| Orchestrator[Liveness Orchestrator]
    Orchestrator -->|select challenge| Challenge[Active Challenge Controller]
    Challenge -->|prompt| UI[Capture / Auth UI]
    UI -->|subsequent frames| Streamer
    Orchestrator -->|accept / reject| Workflow[Registration or Auth Workflow]
    Orchestrator --> Audit[Audit / Diagnostic Log]
    Config[Liveness Config Store] --> Orchestrator
    Config --> Engine
```

- **Device Adapter Layer** — isolates vendor SDKs behind one interface (`FaceFrameSource`), so the engine never talks to a specific vendor's SDK directly. This is what "remain independent of any specific biometric vendor" in the spec requires.
- **Liveness / PAD Engine** — stateless scorer. Given a frame (or short window of frames), returns a passive liveness score + PAD verdict. Runs fully on-device (no network call).
- **Liveness Orchestrator** — the state machine described in the spec (passive → threshold check → active challenge → accept/retry/reject). This is the piece that's identical across resident registration, operator auth, and supervisor auth — those three just call the same orchestrator with a different "policy" from config.
- **Active Challenge Controller** — randomly selects a challenge type, tracks landmark state across the frame window, decides pass/fail.
- **Config Store** — per the spec: enable/disable, thresholds, challenge types, timeout, max retries, per-workflow policy.
- **Audit Log** — PAD failure detail goes here only; the UI only ever sees a generic message.

## 2. Sequence diagram — resident registration path

```mermaid
sequenceDiagram
    participant R as Resident
    participant UI as Capture UI
    participant O as Liveness Orchestrator
    participant E as Liveness/PAD Engine
    participant C as Challenge Controller
    participant D as Device Adapter

    UI->>D: start capture
    D-->>UI: face frame stream
    UI->>O: submit frame(s)
    O->>E: evaluatePassive(frames)
    E-->>O: score, padVerdict

    alt score >= threshold and no PAD attack
        O-->>UI: accept capture
    else score < threshold or PAD suspected
        O->>C: selectChallenge()
        C-->>UI: "Please blink" (system-chosen, not user-chosen)
        UI->>D: continue streaming
        D-->>UI: subsequent frames
        UI->>O: submit frames
        O->>C: evaluateChallenge(frames, challenge)
        C-->>O: pass/fail
        alt pass
            O-->>UI: accept capture
        else fail and retries remain
            O-->>UI: retry (new random challenge)
        else max retries exceeded
            O-->>UI: reject, show recovery guidance
            O->>Audit: log failure detail
        end
    end
```

Operator and supervisor authentication reuse this exact same diagram — only the trigger point and the config policy differ (see `LivenessConfig.workflow`).

## 3. Passive → Active decision logic

1. Passive engine returns `score ∈ [0,1]` and `padDetected: boolean` (+ optional `attackType` for audit only).
2. If `score >= config.passiveThreshold && !padDetected` → **accept immediately**, no user friction.
3. Else → **enter active mode**: pick one challenge at random from `config.enabledChallengeTypes`, never letting the resident/operator choose it.
4. Active mode re-runs the passive/PAD check on every incoming frame *in addition to* validating the requested action — a live person performing the wrong action, or a static image being puppeted, should still fail.
5. On success → accept. On failure → retry up to `config.maxRetries`, then hard-fail with generic UI message + detailed audit log entry.

## 4. Offline-first constraint

Everything above must run with zero network calls. The only thing allowed to touch the network is a background **model sync** job (new PAD model weights, new challenge types) that swaps in a validated model file when connectivity is available — never blocking or altering the live decision path.

## 5. ISO/IEC 30107 alignment notes

- Passive engine output should be tunable via a single **APCER/BPCER trade-off threshold**, not a hardcoded cutoff — this maps directly to `config.passiveThreshold`.
- PAD attack categories to explicitly test against: print attack, screen replay, video replay (per spec) — the bonus "mock device + automated PAD attack scenarios" task is really an ISO/IEC 30107-3 style test harness in miniature.
- Keep APCER/BPCER numbers from your test set in the technical design doc — judges will be looking for this, not just a demo video.
