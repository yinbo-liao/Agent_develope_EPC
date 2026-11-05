# Red-team baseline

`api/eval/red_team.jsonl` is a deterministic regression corpus for the risk
classifier. It covers:

- benign requests (low),
- destructive/credential/bulk-data requests (high),
- destructive, financial, privilege-escalation, prompt-injection, system-prompt
  exfiltration and approval-bypass requests (critical).

Run it from `api/`:

```bash
python scripts/run_eval.py            # exits non-zero below 100%
python scripts/run_eval.py --min-pass-rate 0.9
```

CI runs it as a required evidence check (`--check "eval=python scripts/run_eval.py"`).

This is a **classification baseline**, not an end-to-end model evaluation. It proves
known unsafe prompts do not silently fall into a lower risk tier; it does not score
answer quality, retrieval or tool use.