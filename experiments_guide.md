# Experiments Guide — Scoring Agent-Built Models

How to measure how accurately the Langflow agent reconstructs a ground-truth
PyFlow model. All commands are run from the repo root using the project venv
(`.venv\Scripts\python.exe`).

**Loop:** generate ground truth → capture the agent's model → score the two.

---

## 0. One-time setup — generate the ground-truth references

The reference models live in `pyflow_mcp/reference_models.py` (single source of
truth). Emit their JSONs into `references/`:

```powershell
.\.venv\Scripts\python.exe -m pyflow_mcp.reference_models        # model1, model2, model3
```

Produces `references/model1.json`, `references/model2.json`, `references/model3.json`.
`model3` is also (re)written whenever you run `test_I3M.py` with `MODEL = 3`.

---

## 1. BEFORE prompting — start the MCP server with capture ON

The scorer needs the agent's constructed model on disk. Capture is **off by
default**; turn it on for the experiment session, then start the server:

```powershell
$env:PYFLOW_MCP_CAPTURE = "1"
$env:PYFLOW_MCP_RUN_ID  = "gpt_run1"     # optional: names the capture file & CSV row
.\.venv\Scripts\python.exe pyflow_mcp\server.py
```

Point Langflow's MCP tool at the printed SSE URL (default `http://127.0.0.1:8000/sse`).

> If `PYFLOW_MCP_RUN_ID` is omitted, each build gets a timestamped filename.
> Set a fresh id (or leave it to the timestamp) for every new experiment.

---

## 2. DURING — run the prompt in Langflow

The agent builds the model through the MCP tools and, as its final build step,
calls `initialize_model`. That call auto-writes the model to:

```
experiments\model_<run-id>.json
```

in the same shape as the `describe_model` tool output. Nothing else is needed —
the chat report the agent produces is unaffected.

> No file written? The agent never reached `initialize_model`, or capture was
> off. You can still score by saving the agent's `describe_model` JSON manually
> and passing it with `--candidate <file>` in the next step.

---

## 3. AFTER the LLM output — score the model structure

Score the newest capture against the matching ground truth:

```powershell
.\.venv\Scripts\python.exe -m pyflow_mcp.score_experiment --latest --model model3
```

Use `--model model1` / `--model model2` for the other targets, or
`--candidate experiments\model_gpt_run1.json` to score a specific file.

**Output:** a report printed to the console plus, in `experiments\`:

- `model_<run-id>_report.txt` / `.json` — full breakdown + diagnostics.
- `summary.csv` — one row per run (appended), for comparing experiments.

Headline numbers:

| Metric | Meaning |
|---|---|
| **Elements well built** | % of ground-truth elements reproduced with all key params correct (your model-construction accuracy) |
| Overall score | Weighted total: element types 25% · parameters 30% · topology 30% · strategy 15% |
| Breakdown | Per-dimension scores; report lists every missing element, missing connection, strategy and parameter mismatch |

Matching is **id-agnostic** — the agent may name elements differently and still
score 100%.

---

## Quick reference

| Item | Location |
|---|---|
| Ground-truth definitions | `pyflow_mcp/reference_models.py` |
| Reference JSONs | `references/modelN.json` |
| Agent captures | `experiments/model_<run-id>.json` |
| Reports + summary | `experiments/*_report.*`, `experiments/summary.csv` |
| Scorer (harness-only, not an MCP tool) | `pyflow_mcp/structural_score.py` |

| Env var | Purpose | Default |
|---|---|---|
| `PYFLOW_MCP_CAPTURE` | `1` to enable capture on `initialize_model` | off |
| `PYFLOW_MCP_RUN_ID` | Fixed capture id / CSV run label | timestamp |
| `PYFLOW_MCP_EXPERIMENT_DIR` | Output directory | `experiments` |

Experiment artifacts in `experiments/` are git-ignored.
