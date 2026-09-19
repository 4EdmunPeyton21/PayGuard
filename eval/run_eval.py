import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.schemas.case import NormalisedCase

from eval.metrics import calculate_metrics, print_comparative_table


def load_cases(dataset_path: Path, split: str) -> list:
    cases = []
    if not dataset_path.exists():
        print(f"Dataset not found at {dataset_path}")
        return cases

    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            if split == "all" or data.get("split") == split:
                cases.append(data)
    return cases


def main():
    parser = argparse.ArgumentParser(description="PayGuard Evaluation Harness")
    parser.add_argument(
        "--arm",
        type=str,
        required=True,
        choices=["arm0", "arm1", "arm2", "arm3"],
        help="Which pipeline arm to evaluate",
    )
    parser.add_argument(
        "--split",
        type=str,
        default="all",
        help="Dataset split to run on (default: all)",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    dataset_path = base_dir / "dataset" / "cases.jsonl"

    cases_data = load_cases(dataset_path, args.split)
    print(f"Loaded {len(cases_data)} cases for split '{args.split}'.")

    if not cases_data:
        return

    # Load the requested arm
    if args.arm == "arm0":
        from eval.arms.arm0_deterministic import run_arm0 as run_arm
    elif args.arm == "arm1":
        from eval.arms.arm1_baseline_llm import run_arm1 as run_arm
    elif args.arm == "arm2":
        from eval.arms.arm2_agent_tools import run_arm2 as run_arm
    else:
        print(f"Arm '{args.arm}' is not yet implemented.")
        return

    run_id = f"{args.arm}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    results_dir = base_dir / "results" / run_id
    results_dir.mkdir(parents=True, exist_ok=True)
    results_path = results_dir / "results.jsonl"

    print(f"Running evaluation on {len(cases_data)} cases using {args.arm}...")
    print(f"Results will be written to {results_path}\n")

    results = []
    for i, cdata in enumerate(cases_data):
        case = NormalisedCase(
            case_id=cdata["case_id"],
            input_types=["text"],
            text=cdata["text"],
            text_source="user",
        )

        try:
            report = run_arm(case)
            predicted_level = report.risk_level
            predicted_signals = [e.signal.value for e in report.evidence]
            tool_calls = report.tool_calls
        except Exception as e:
            print(f"\n[!] Error processing case {cdata['case_id']}: {e}")
            predicted_level = "ERROR"
            predicted_signals = []
            tool_calls = 0

        res_row = {
            "case_id": cdata["case_id"],
            "category": cdata["category"],
            "text": cdata["text"],
            "expected_level": cdata["expected_level"],
            "expected_signals": cdata["expected_signals"],
            "predicted_level": predicted_level,
            "predicted_signals": predicted_signals,
            "tool_calls": tool_calls,
        }
        results.append(res_row)

        with open(results_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(res_row) + "\n")

        print(
            f"[{i+1}/{len(cases_data)}] {cdata['case_id']:<15} -> "
            f"Predicted: {predicted_level:<12} (Expected: {cdata['expected_level']})"
        )

    # Calculate single run metrics
    calculate_metrics(str(results_path))

    # Print cross-arm comparison table
    print_comparative_table(base_dir / "results")


if __name__ == "__main__":
    main()
