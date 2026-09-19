# PayGuard Evaluation Results

Test split: 90 cases. Each arm run 3x; policy tuned on the
dev split only, before this script was ever run against test (see
policy_v1.yaml/lexicon.yaml comments for the dev-split findings that
justified each change). No policy or lexicon edits followed a test run.

## Summary (mean ± std over 3 runs, test split)

| Arm | Accuracy | FPR | FNR | Evidence Precision | Evidence Recall | Mean Tool Calls |
|---|---|---|---|---|---|---|
| Arm 0 (Deterministic) | 97.78% ± 0.00% | 0.00% ± 0.00% | 4.88% ± 0.00% | 100.00% ± 0.00% | 97.22% ± 0.00% | 2.66 ± 0.00 |
| Arm 1 (Baseline LLM) | 45.56% ± 0.00% | 100.00% ± 0.00% | 0.00% ± 0.00% | 0.00% ± 0.00% | 0.00% ± 0.00% | 0.00 ± 0.00 |
| Arm 2 (Agent + Tools) | 86.67% ± 0.00% | 0.00% ± 0.00% | 29.27% ± 0.00% | 100.00% ± 0.00% | 32.96% ± 0.00% | 1.00 ± 0.00 |
| Arm 3 (Fine-tuned) | not run, see §15 | -- | -- | -- | -- | -- |

## Bootstrap 95% CI on accuracy (first run, n=1000 resamples)

| Arm | Accuracy | 95% CI |
|---|---|---|
| Arm 0 (Deterministic) | 97.78% | [94.44%, 100.00%] |
| Arm 1 (Baseline LLM) | 45.56% | [35.56%, 55.56%] |
| Arm 2 (Agent + Tools) | 86.67% | [80.00%, 93.33%] |

## False positive rate on the hard-negative subset

The `legitimate_hard_negative` category (D4) is the set most likely to
reveal over-eager flagging: legitimate messages that look risky on the
surface (real OTP delivery, official links, urgent-but-true reminders).

| Arm | Hard-Negative FPR (run 1) |
|---|---|
| Arm 0 (Deterministic) | 0.00% |
| Arm 1 (Baseline LLM) | 100.00% |
| Arm 2 (Agent + Tools) | 0.00% |

## Known limitations

- Arm 1 and Arm 2 both depend on a real LLM endpoint; in an environment
  where that endpoint is unreachable, Arm 1 always returns its exception
  fallback (CAUTION) and Arm 2's agent loop always falls through to the
  deterministic gap-checker + template narrator. Both are still reported
  because that fallback behavior is itself part of the system's design
  (D14/D16), but the numbers above do not reflect a live LLM's judgment.
- Several Signal enum members that policy_v1.yaml and patterns.yaml were
  already written to expect (otp_request, pin_request, payment_request,
  unsolicited_refund, job_offer_fee, upi_collect_request,
  remote_access_request, investment_promise, sender_verified_channel)
  were never wired into signal_scan.py's lexicon until this pass -- found
  by the D24 adversarial cases and fixed here using dev-split evidence.
