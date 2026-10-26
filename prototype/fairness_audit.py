"""
Fairness / bias audit harness for the liveness engine.

Face PAD and liveness models are well documented in the research
literature to perform unevenly across skin tones and lighting conditions
-- exactly the diversity MOSIP's real deployments span (30+ countries
across Asia-Pacific, Africa, Latin America, the Caribbean). Reporting
disaggregated error rates, not just an aggregate accuracy number, is
rare in hackathon submissions and directly demonstrates production-
readiness and awareness of real-world equity concerns -- both explicit
MOSIP values ("inclusive... digital identity systems").

Usage:
    python fairness_audit.py --manifest test_manifest.csv

test_manifest.csv columns:
    filepath, label, skin_tone_bucket, lighting_bucket
      label:            "live" or "attack"
      skin_tone_bucket:  e.g. "I-II", "III-IV", "V-VI"  (Fitzpatrick-scale-style buckets)
      lighting_bucket:   e.g. "bright", "dim", "backlit"

Outputs a disaggregated APCER/BPCER table per (skin_tone_bucket, lighting_bucket)
and flags any bucket whose error rate deviates from the overall rate beyond
a configurable tolerance -- this table is exactly what to paste into the
"Security and privacy considerations" section of the technical design doc.
"""

import argparse
import csv
from collections import defaultdict

import cv2

from liveness_engine import LivenessEngine


def load_manifest(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def run_audit(manifest_path: str, threshold: float, tolerance: float = 0.05):
    engine = LivenessEngine()
    engine.PASSIVE_SCORE_THRESHOLD = threshold

    rows = load_manifest(manifest_path)
    buckets = defaultdict(lambda: {"attacks_total": 0, "attacks_passed": 0, "live_total": 0, "live_rejected": 0})
    overall = {"attacks_total": 0, "attacks_passed": 0, "live_total": 0, "live_rejected": 0}

    for row in rows:
        frame = cv2.imread(row["filepath"])
        if frame is None:
            print(f"WARN: could not read {row['filepath']}, skipping")
            continue

        result = engine.evaluate_passive(frame)
        accepted = (result.score >= threshold) and not result.pad_detected

        key = (row["skin_tone_bucket"], row["lighting_bucket"])

        if row["label"] == "attack":
            buckets[key]["attacks_total"] += 1
            overall["attacks_total"] += 1
            if accepted:
                buckets[key]["attacks_passed"] += 1  # this is an APCER error (attack let through)
                overall["attacks_passed"] += 1
        else:  # live
            buckets[key]["live_total"] += 1
            overall["live_total"] += 1
            if not accepted:
                buckets[key]["live_rejected"] += 1  # this is a BPCER error (real user rejected)
                overall["live_rejected"] += 1

    def rate(numerator, denominator):
        return (numerator / denominator) if denominator else float("nan")

    overall_apcer = rate(overall["attacks_passed"], overall["attacks_total"])
    overall_bpcer = rate(overall["live_rejected"], overall["live_total"])

    print(f"\n{'Skin tone':<10} {'Lighting':<10} {'APCER':>8} {'BPCER':>8} {'n(attack)':>10} {'n(live)':>9}  Flag")
    print("-" * 70)
    flagged = []
    for (skin, light), counts in sorted(buckets.items()):
        apcer = rate(counts["attacks_passed"], counts["attacks_total"])
        bpcer = rate(counts["live_rejected"], counts["live_total"])
        flag = ""
        if apcer == apcer and abs(apcer - overall_apcer) > tolerance:  # NaN-safe check
            flag += "APCER-GAP "
        if bpcer == bpcer and abs(bpcer - overall_bpcer) > tolerance:
            flag += "BPCER-GAP"
        if flag:
            flagged.append((skin, light, flag))
        print(f"{skin:<10} {light:<10} {apcer:>7.2%} {bpcer:>7.2%} {counts['attacks_total']:>10} {counts['live_total']:>9}  {flag}")

    print("-" * 70)
    print(f"{'OVERALL':<21} {overall_apcer:>7.2%} {overall_bpcer:>7.2%} {overall['attacks_total']:>10} {overall['live_total']:>9}")

    if flagged:
        print(f"\n{len(flagged)} bucket(s) deviate from overall error rate by more than {tolerance:.0%}:")
        for skin, light, flag in flagged:
            print(f"  - {skin} / {light}: {flag}")
    else:
        print("\nNo buckets exceeded the fairness tolerance.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, help="CSV: filepath,label,skin_tone_bucket,lighting_bucket")
    parser.add_argument("--threshold", type=float, default=0.6)
    parser.add_argument("--tolerance", type=float, default=0.05, help="max allowed deviation from overall error rate")
    args = parser.parse_args()
    run_audit(args.manifest, args.threshold, args.tolerance)
