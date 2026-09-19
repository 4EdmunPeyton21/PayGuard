import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Optional


def calculate_metrics(results_path: str) -> Dict[str, Any]:
    path = Path(results_path)
    if not path.exists():
        print(f"Results file not found: {results_path}")
        return {}

    with open(path, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    total = len(lines)
    if total == 0:
        print("No results to evaluate.")
        return {}

    y_true_bin = []
    y_pred_bin = []
    cm = defaultdict(lambda: defaultdict(int))

    ev_precisions = []
    ev_recalls = []
    tool_calls = []

    for row in lines:
        exp_lvl = row["expected_level"]
        pred_lvl = row.get("predicted_level", "ERROR")
        cm[exp_lvl][pred_lvl] += 1
        if "tool_calls" in row:
            tool_calls.append(row["tool_calls"])

        # Binary definition: Flagged (HIGH_RISK or CAUTION) vs Not Flagged (LOW_CONCERN)
        is_exp_flagged = exp_lvl in ("HIGH_RISK", "CAUTION")
        is_pred_flagged = pred_lvl in ("HIGH_RISK", "CAUTION")
        y_true_bin.append(is_exp_flagged)
        y_pred_bin.append(is_pred_flagged)

        # Evidence Precision and Recall
        exp_sigs = set(row.get("expected_signals", []))
        pred_sigs = set(row.get("predicted_signals", []))

        if exp_sigs:
            overlap = len(exp_sigs & pred_sigs)
            ev_recalls.append(overlap / len(exp_sigs))
        if pred_sigs:
            overlap = len(exp_sigs & pred_sigs)
            ev_precisions.append(overlap / len(pred_sigs))
        elif not exp_sigs and not pred_sigs:
            ev_precisions.append(1.0)
            ev_recalls.append(1.0)

    tp = sum(1 for t, p in zip(y_true_bin, y_pred_bin, strict=False) if t and p)
    tn = sum(1 for t, p in zip(y_true_bin, y_pred_bin, strict=False) if not t and not p)
    fp = sum(1 for t, p in zip(y_true_bin, y_pred_bin, strict=False) if not t and p)
    fn = sum(1 for t, p in zip(y_true_bin, y_pred_bin, strict=False) if t and not p)

    acc = (tp + tn) / total if total > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0

    avg_ev_p = sum(ev_precisions) / len(ev_precisions) if ev_precisions else 0.0
    avg_ev_r = sum(ev_recalls) / len(ev_recalls) if ev_recalls else 0.0
    avg_tool_calls = sum(tool_calls) / len(tool_calls) if tool_calls else 0.0

    print("\n" + "=" * 70)
    print(f"RUN METRICS (n={total})")
    print("=" * 70)
    print(f"Accuracy (Flagged vs Not): {acc:.2%}")
    print(f"False Positive Rate (FPR): {fpr:.2%}")
    print(f"False Negative Rate (FNR): {fnr:.2%}")
    print(f"Evidence Precision:        {avg_ev_p:.2%}")
    print(f"Evidence Recall:           {avg_ev_r:.2%}")
    print(f"Mean Tool Calls:           {avg_tool_calls:.2f}")

    print("\nCONFUSION MATRIX (Rows: True, Cols: Predicted):")
    levels = ["HIGH_RISK", "CAUTION", "LOW_CONCERN", "ERROR"]
    label = "True / Pred"
    print(f"{label:>15} | " + " | ".join(f"{lvl:>11}" for lvl in levels))
    print("-" * 70)
    for t_lvl in levels[:-1]:
        row_str = f"{t_lvl:>15} | "
        for p_lvl in levels:
            row_str += f"{cm[t_lvl][p_lvl]:>11} | "
        print(row_str)
    print("=" * 70 + "\n")

    return {
        "total": total,
        "accuracy": acc,
        "fpr": fpr,
        "fnr": fnr,
        "evidence_precision": avg_ev_p,
        "evidence_recall": avg_ev_r,
        "mean_tool_calls": avg_tool_calls,
        "confusion_matrix": {k: dict(v) for k, v in cm.items()},
    }


def print_comparative_table(results_dir: Path) -> None:
    """Find latest runs for all evaluated arms and display side-by-side comparison."""
    if not results_dir.exists():
        return

    known_arms = ["arm0", "arm1", "arm2", "arm3"]
    arm_labels = {
        "arm0": "Arm 0 (Deterministic)",
        "arm1": "Arm 1 (Baseline LLM)",
        "arm2": "Arm 2 (Agent + Tools)",
        "arm3": "Arm 3 (Fine-tuned)",
    }

    arm_metrics: Dict[str, Dict[str, Any]] = {}

    for arm in known_arms:
        # Find all run folders for this arm
        run_dirs = sorted(results_dir.glob(f"{arm}_*"))
        if not run_dirs:
            continue
        latest_run = run_dirs[-1]
        res_file = latest_run / "results.jsonl"
        if res_file.exists():
            # Quietly compute metrics
            m = _compute_metrics_silent(res_file)
            if m:
                arm_metrics[arm] = m

    if not arm_metrics:
        return

    # Print comparison table
    active_arms = list(arm_metrics.keys())
    col_width = 24
    header = f"{'Metric':<25} | " + " | ".join(f"{arm_labels[a]:<{col_width}}" for a in active_arms)
    divider = "=" * len(header)

    print("\n" + divider)
    print("PAYGUARD CROSS-ARM BENCHMARK COMPARISON")
    print(divider)
    print(header)
    print("-" * len(header))

    metrics_to_show = [
        ("Accuracy (Flagged)", lambda m: f"{m['accuracy']:.2%}"),
        ("False Positive Rate", lambda m: f"{m['fpr']:.2%}"),
        ("False Negative Rate", lambda m: f"{m['fnr']:.2%}"),
        ("Evidence Precision", lambda m: f"{m['evidence_precision']:.2%}"),
        ("Evidence Recall", lambda m: f"{m['evidence_recall']:.2%}"),
        ("Mean Tool Calls", lambda m: f"{m['mean_tool_calls']:.2f}"),
        ("Evaluated Cases", lambda m: f"{m['total']}"),
    ]

    for name, fmt in metrics_to_show:
        vals = " | ".join(f"{fmt(arm_metrics[a]):<{col_width}}" for a in active_arms)
        row = f"{name:<25} | " + vals
        print(row)

    print(divider + "\n")


def _compute_metrics_silent(results_path: Path) -> Optional[Dict[str, Any]]:
    with open(results_path, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    total = len(lines)
    if total == 0:
        return None

    y_true_bin = []
    y_pred_bin = []
    ev_precisions = []
    ev_recalls = []
    tool_calls = []

    for row in lines:
        exp_lvl = row["expected_level"]
        pred_lvl = row.get("predicted_level", "ERROR")
        is_exp = exp_lvl in ("HIGH_RISK", "CAUTION")
        is_pred = pred_lvl in ("HIGH_RISK", "CAUTION")
        y_true_bin.append(is_exp)
        y_pred_bin.append(is_pred)
        if "tool_calls" in row:
            tool_calls.append(row["tool_calls"])

        exp_sigs = set(row.get("expected_signals", []))
        pred_sigs = set(row.get("predicted_signals", []))

        if exp_sigs:
            ev_recalls.append(len(exp_sigs & pred_sigs) / len(exp_sigs))
        if pred_sigs:
            ev_precisions.append(len(exp_sigs & pred_sigs) / len(pred_sigs))
        elif not exp_sigs and not pred_sigs:
            ev_precisions.append(1.0)
            ev_recalls.append(1.0)

    tp = sum(1 for t, p in zip(y_true_bin, y_pred_bin, strict=False) if t and p)
    tn = sum(1 for t, p in zip(y_true_bin, y_pred_bin, strict=False) if not t and not p)
    fp = sum(1 for t, p in zip(y_true_bin, y_pred_bin, strict=False) if not t and p)
    fn = sum(1 for t, p in zip(y_true_bin, y_pred_bin, strict=False) if t and not p)

    return {
        "total": total,
        "accuracy": (tp + tn) / total if total > 0 else 0.0,
        "fpr": fp / (fp + tn) if (fp + tn) > 0 else 0.0,
        "fnr": fn / (fn + tp) if (fn + tp) > 0 else 0.0,
        "evidence_precision": sum(ev_precisions) / len(ev_precisions) if ev_precisions else 0.0,
        "evidence_recall": sum(ev_recalls) / len(ev_recalls) if ev_recalls else 0.0,
        "mean_tool_calls": sum(tool_calls) / len(tool_calls) if tool_calls else 0.0,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        calculate_metrics(sys.argv[1])
