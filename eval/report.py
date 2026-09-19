"""D25: Tune and report.

Runs Arms 0/1/2 three times each on the TEST split, reports mean +/- std
across those 3 runs per metric, a bootstrap 95% CI on accuracy from one
run's per-case results, and FPR broken out for the legitimate_hard_negative
subset specifically. Writes results/RESULTS.md.

Arm 3 (fine-tuned) is not run -- deferred per plan.md Section 15: there is
no route to serve a LoRA adapter through the NIM-hosted endpoint inside
the hackathon window.

This script only READS the dataset and the already-tuned policy; it does
not adjust policy_v1.yaml or the lexicon. Tuning (dev-split only) happened
before this script was written -- see the sender_verified_channel /
delivery_otp_in_person / alarm_without_actionable_request additions in
policy_v1.yaml and lexicon.yaml, all justified from dev-split findings,
never from a peek at test results.

Run: python eval/report.py
"""
import importlib
import json
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

backend_dir = Path(__file__).resolve().parent.parent / "backend"
eval_dir = Path(__file__).resolve().parent
for p in (str(backend_dir), str(eval_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.schemas.case import NormalisedCase  # noqa: E402


def load_cases(dataset_path: Path, split: str) -> List[dict]:
    """Local copy of run_eval.load_cases -- avoids importing run_eval.py as
    a library, which assumes the repo root (not eval/) is on sys.path."""
    cases = []
    with open(dataset_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if split == "all" or data.get("split") == split:
                cases.append(data)
    return cases


ARMS: Dict[str, Tuple[str, str, str]] = {
    "arm0": ("Arm 0 (Deterministic)", "arms.arm0_deterministic", "run_arm0"),
    "arm1": ("Arm 1 (Baseline LLM)", "arms.arm1_baseline_llm", "run_arm1"),
    "arm2": ("Arm 2 (Agent + Tools)", "arms.arm2_agent_tools", "run_arm2"),
}

N_RUNS = 3
BOOTSTRAP_SAMPLES = 1000
HARD_NEGATIVE_CATEGORY = "legitimate_hard_negative"
OUT_PATH = Path(__file__).resolve().parent.parent / "results" / "RESULTS.md"


def _load_arm(arm_key: str) -> Callable[[NormalisedCase], object]:
    _, module_name, func_name = ARMS[arm_key]
    module = importlib.import_module(module_name)
    return getattr(module, func_name)


def _run_once(run_fn: Callable, cases: List[dict]) -> List[dict]:
    rows = []
    for cdata in cases:
        case = NormalisedCase(
            case_id=cdata["case_id"], input_types=["text"], text=cdata["text"], text_source="user"
        )
        try:
            report = run_fn(case)
            predicted_level = report.risk_level
            predicted_signals = [e.signal.value for e in report.evidence]
            tool_calls = report.tool_calls
        except Exception:
            predicted_level = "ERROR"
            predicted_signals = []
            tool_calls = 0
        rows.append(
            {
                **cdata,
                "predicted_level": predicted_level,
                "predicted_signals": predicted_signals,
                "tool_calls": tool_calls,
            }
        )
    return rows


def _binary_metrics(rows: List[dict]) -> Dict[str, float]:
    total = len(rows)
    y_true = [r["expected_level"] in ("HIGH_RISK", "CAUTION") for r in rows]
    y_pred = [r["predicted_level"] in ("HIGH_RISK", "CAUTION") for r in rows]
    tp = sum(1 for t, p in zip(y_true, y_pred, strict=False) if t and p)
    tn = sum(1 for t, p in zip(y_true, y_pred, strict=False) if not t and not p)
    fp = sum(1 for t, p in zip(y_true, y_pred, strict=False) if not t and p)
    fn = sum(1 for t, p in zip(y_true, y_pred, strict=False) if t and not p)

    ev_p, ev_r = [], []
    for r in rows:
        exp = set(r["expected_signals"])
        pred = set(r["predicted_signals"])
        if exp:
            ev_r.append(len(exp & pred) / len(exp))
        if pred:
            ev_p.append(len(exp & pred) / len(pred))
        elif not exp and not pred:
            ev_p.append(1.0)
            ev_r.append(1.0)

    return {
        "accuracy": (tp + tn) / total if total else 0.0,
        "fpr": fp / (fp + tn) if (fp + tn) else 0.0,
        "fnr": fn / (fn + tp) if (fn + tp) else 0.0,
        "evidence_precision": sum(ev_p) / len(ev_p) if ev_p else 0.0,
        "evidence_recall": sum(ev_r) / len(ev_r) if ev_r else 0.0,
        "mean_tool_calls": sum(r["tool_calls"] for r in rows) / total if total else 0.0,
    }


def _bootstrap_accuracy_ci(
    rows: List[dict], n: int = BOOTSTRAP_SAMPLES, seed: int = 42
) -> Tuple[float, float]:
    rng = random.Random(seed)
    n_rows = len(rows)
    accuracies = []
    for _ in range(n):
        sample = [rows[rng.randrange(n_rows)] for _ in range(n_rows)]
        accuracies.append(_binary_metrics(sample)["accuracy"])
    accuracies.sort()
    lo = accuracies[int(0.025 * n)]
    hi = accuracies[min(int(0.975 * n), n - 1)]
    return lo, hi


def _hard_negative_fpr(rows: List[dict]) -> Optional[float]:
    subset = [r for r in rows if r["category"] == HARD_NEGATIVE_CATEGORY]
    if not subset:
        return None
    flagged = sum(1 for r in subset if r["predicted_level"] in ("HIGH_RISK", "CAUTION"))
    return flagged / len(subset)


def _mean_std(values: List[float]) -> Tuple[float, float]:
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return mean, std


def main() -> None:
    dataset_path = Path(__file__).resolve().parent / "dataset" / "cases.jsonl"
    cases = load_cases(dataset_path, "test")
    print(f"Loaded {len(cases)} test-split cases.\n")

    per_arm_runs: Dict[str, List[List[dict]]] = {}
    per_arm_metrics: Dict[str, List[Dict[str, float]]] = {}

    for arm_key, (label, _, _) in ARMS.items():
        print(f"=== {label}: {N_RUNS} runs on test split ===")
        run_fn = _load_arm(arm_key)
        runs = []
        metrics_list = []
        for run_i in range(N_RUNS):
            t0 = time.perf_counter()
            rows = _run_once(run_fn, cases)
            m = _binary_metrics(rows)
            elapsed = time.perf_counter() - t0
            print(
                f"  run {run_i + 1}/{N_RUNS}: accuracy={m['accuracy']:.2%} "
                f"fpr={m['fpr']:.2%} fnr={m['fnr']:.2%} ({elapsed:.1f}s)"
            )
            runs.append(rows)
            metrics_list.append(m)
        per_arm_runs[arm_key] = runs
        per_arm_metrics[arm_key] = metrics_list
        print()

    lines = [
        "# PayGuard Evaluation Results",
        "",
        f"Test split: {len(cases)} cases. Each arm run {N_RUNS}x; policy tuned on the",
        "dev split only, before this script was ever run against test (see",
        "policy_v1.yaml/lexicon.yaml comments for the dev-split findings that",
        "justified each change). No policy or lexicon edits followed a test run.",
        "",
        "## Summary (mean ± std over 3 runs, test split)",
        "",
        "| Arm | Accuracy | FPR | FNR | Evidence Precision | Evidence Recall | Mean Tool Calls |",
        "|---|---|---|---|---|---|---|",
    ]

    metric_keys = ["accuracy", "fpr", "fnr", "evidence_precision", "evidence_recall"]
    for arm_key, (label, _, _) in ARMS.items():
        metrics_list = per_arm_metrics[arm_key]
        cells = [label]
        for key in metric_keys:
            mean, std = _mean_std([m[key] for m in metrics_list])
            cells.append(f"{mean:.2%} ± {std:.2%}")
        tool_calls_mean, tool_calls_std = _mean_std([m["mean_tool_calls"] for m in metrics_list])
        cells.append(f"{tool_calls_mean:.2f} ± {tool_calls_std:.2f}")
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("| Arm 3 (Fine-tuned) | not run, see §15 | -- | -- | -- | -- | -- |")

    lines += [
        "",
        "## Bootstrap 95% CI on accuracy (first run, n=1000 resamples)",
        "",
        "| Arm | Accuracy | 95% CI |",
        "|---|---|---|",
    ]
    for arm_key, (label, _, _) in ARMS.items():
        first_run = per_arm_runs[arm_key][0]
        acc = per_arm_metrics[arm_key][0]["accuracy"]
        lo, hi = _bootstrap_accuracy_ci(first_run)
        lines.append(f"| {label} | {acc:.2%} | [{lo:.2%}, {hi:.2%}] |")

    lines += [
        "",
        "## False positive rate on the hard-negative subset",
        "",
        "The `legitimate_hard_negative` category (D4) is the set most likely to",
        "reveal over-eager flagging: legitimate messages that look risky on the",
        "surface (real OTP delivery, official links, urgent-but-true reminders).",
        "",
        "| Arm | Hard-Negative FPR (run 1) |",
        "|---|---|",
    ]
    for arm_key, (label, _, _) in ARMS.items():
        fpr = _hard_negative_fpr(per_arm_runs[arm_key][0])
        lines.append(f"| {label} | {fpr:.2%} |" if fpr is not None else f"| {label} | n/a |")

    lines += [
        "",
        "## Known limitations",
        "",
        "- Arm 1 and Arm 2 both depend on a real LLM endpoint; in an environment",
        "  where that endpoint is unreachable, Arm 1 always returns its exception",
        "  fallback (CAUTION) and Arm 2's agent loop always falls through to the",
        "  deterministic gap-checker + template narrator. Both are still reported",
        "  because that fallback behavior is itself part of the system's design",
        "  (D14/D16), but the numbers above do not reflect a live LLM's judgment.",
        "- Several Signal enum members that policy_v1.yaml and patterns.yaml were",
        "  already written to expect (otp_request, pin_request, payment_request,",
        "  unsolicited_refund, job_offer_fee, upi_collect_request,",
        "  remote_access_request, investment_promise, sender_verified_channel)",
        "  were never wired into signal_scan.py's lexicon until this pass -- found",
        "  by the D24 adversarial cases and fixed here using dev-split evidence.",
        "",
    ]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
