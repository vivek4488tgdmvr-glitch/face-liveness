# Why this submission is hard to copy

Most teams on this problem statement will converge on the same shape: a CNN passive
score + blink/turn/smile active challenges. That's the correct baseline — it's also
exactly what every other submission will look like. Three additions push past that
baseline in ways that are technically substantive and hard to reproduce in a hackathon
timeframe, and that map directly onto what MOSIP itself is built to care about.

## 1. Dual-signal liveness: texture/frequency PAD + rPPG pulse detection

`prototype/rppg_liveness.py`

A live human's face shows tiny, periodic color shifts in sync with their heartbeat,
extractable from ordinary video by averaging the green channel over the forehead
region and finding a dominant frequency in the 42–240 bpm band. A printed photo has
no pulse. A static mask has no pulse. Most naive screen-replay setups don't preserve
it either.

This is fused with the existing texture/frequency PAD score as a second, largely
*independent* signal — an attacker now has to defeat two different physical
properties (surface texture/frequency artifacts, and a real physiological rhythm)
rather than one. It's also a legitimately interesting thing to explain live in a
judging round, and very few student teams implement it because it requires knowing
it's a viable technique at all, not because it's hard to code once you do.

**Talking point for judges:** "We don't just ask 'does this look like a real face,'
we ask 'is there a heartbeat.'"

## 2. Accessibility-adaptive challenge selection

`interfaces/AccessibilityChallengePolicy.java`

MOSIP's stated mission is inclusive digital ID for populations that other systems
underserve — which explicitly includes elderly residents, residents with motor or
facial impairments, and low-literacy populations. A rigid "turn your head left"
challenge silently fails a resident with limited neck mobility every time, and a
text-only prompt fails an illiterate resident every time. Most competing submissions
will not address this at all.

This policy:
- Tracks per-resident failure patterns and falls back to a different *motion family*
  (e.g. head-turn → blink) after repeated failures, rather than repeating the same
  ask or hard-blocking the person.
- Supports icon- and audio-based prompt delivery alongside text, via a
  `PromptMode` the UI layer can select per deployment/language.
- Never weakens the underlying liveness/PAD decision — it changes *which* legitimate
  challenge is offered and *how* it's communicated, not the security bar itself.

**Talking point for judges:** "A liveness check that a healthy 25-year-old engineer
can pass isn't the same as one that works for the actual population MOSIP serves."

## 3. Fairness/bias audit harness with disaggregated APCER/BPCER

`prototype/fairness_audit.py`

Face PAD and liveness models are documented in the research literature to perform
unevenly across skin tones and lighting conditions — a real risk given MOSIP is
deployed across Asia-Pacific, Africa, Latin America, and the Caribbean, i.e. exactly
the population diversity where this failure mode shows up. This harness runs the
engine against a labeled test manifest (skin-tone bucket × lighting bucket) and
reports APCER/BPCER *per bucket*, flagging any bucket that deviates from the overall
error rate beyond a set tolerance.

Reporting a single aggregate accuracy number is normal for a hackathon demo.
Reporting where your system's error is concentrated, unprompted, is not — and it's
exactly the kind of production-readiness signal a judging panel evaluating for
real-world, multi-country deployment will notice.

**Talking point for judges:** "Here's not just our accuracy — here's where our
system is weakest, and for whom."

## How these fit the ISO/IEC 30107 and technical-design deliverables

All three slot directly into deliverables the problem statement already asks for:
- rPPG fusion → strengthens the "Liveness and PAD processing architecture" section.
- Accessibility policy → strengthens "UI/UX Design" and shows workflow-specific
  policy support beyond the minimum spec.
- Fairness harness output → belongs directly in "Security and privacy
  considerations" / "ISO/IEC 30107 alignment considerations" in the technical
  design doc, with real numbers from your test set.

None of these require ripping up the base architecture already scaffolded — they're
additive modules that plug into the same `LivenessEngine` / `LivenessOrchestrator`
contracts.
