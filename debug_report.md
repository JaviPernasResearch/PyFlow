I now have all the data I need for a comprehensive diagnosis. Here is the full report:

---

# 🔬 MCP Server Diagnostic Report — PyFlow Simulation Tools
**Date:** 2026-05-07 | **Tests Conducted:** 12 distinct test scenarios

---

## ✅ OVERALL VERDICT: The MCP server is **functional and largely working correctly**. Several bugs, inconsistencies, and documentation gaps were identified.

---

## 1. TOOL INVENTORY

| Tool | Status |
|---|---|
| `get_supported_types` | ✅ Works |
| `new_model` | ✅ Works |
| `create_elements_batch` | ✅ Works (with caveats) |
| `connect_batch` | ✅ Works |
| `initialize_model` | ✅ Works |
| `run_experiment` | ✅ Works (with caveats) |
| `get_stats` | ✅ Works |
| `list_elements` | ⚠️ Works but response format inconsistency |
| `list_connections` | ⚠️ Works but response format inconsistency |
| `describe_model` | ✅ Works |
| `get_current_date` | ✅ Works (unrelated utility tool) |

---

## 2. BUGS FOUND

### 🐛 BUG #1 — `InterArrivalSource` stats: `input_count` is always 0, `content_current` is negative
**Severity: Medium**

After a run, the source element reports:
```json
"input_count": 0,
"output_count": 4985,
"content_current": -4985,
"content_average": -1.0
```
A source generates items from nothing, so `input_count = 0` may be intentional, but `content_current = -4985` and `content_average = -1.0` are clearly **nonsensical values** — a content count should never be negative. This appears to be a side effect of computing `content = input - output` without special-casing the source element. The source should either report `content_current = 0` (nothing is "inside" it) or the field should be `null`/omitted for sources.

---

### 🐛 BUG #2 — `run_experiment` wall clock timeout returns wrong `status`
**Severity: Medium**

When `max_wall_seconds` is exceeded, the tool description says the status should be `"wall_clock_timeout"`. However, the actual returned status was:
```json
"status": "network_idle"
```
The run was stopped after 1 chunk (sim time 10,000 out of 1,000,000 requested), and `wall_seconds_elapsed: 2.699` clearly exceeded the `0.5` budget. The status label is wrong — it should be `"wall_clock_timeout"` but instead returns `"network_idle"`, which is a completely different termination reason. This will confuse any agent or user trying to detect timeouts programmatically.

---

### 🐛 BUG #3 — `Sink` stats: `content_current` grows unboundedly, `content_average` is always 1.0
**Severity: Low-Medium**

The Sink accumulates items and never releases them (by design), but the stats show:
```json
"content_current": 4980,
"content_average": 1.0,
"content_max": 4980
```
`content_average = 1.0` is suspicious — it seems like a placeholder or a normalization artifact rather than a meaningful average. Since a Sink is a terminal node, `staytime_*` fields are all 0 (items don't "stay"), which is correct. But `content_average` should either reflect the true time-weighted average occupancy (which would grow over time) or be explicitly documented as "not applicable." The value `1.0` appears to be a bug or an uninitialized default.

---

### 🐛 BUG #4 — Validation errors use MCP-level `isError=True` instead of structured JSON errors
**Severity: Medium**

When invalid parameters are passed (e.g., negative `scale`, unknown element `type`), the server raises a raw Pydantic validation error at the MCP protocol level:
```
isError=True
"Error executing tool create_elements_batch: 1 validation error for create_elements_batchArguments..."
```
This is **inconsistent** with how other errors are handled. For example, duplicate IDs and missing elements return a clean `partial_success` JSON with structured `failed_at` info. Pydantic validation errors should be caught and wrapped in the same structured error format:
```json
{
  "status": "error",
  "error_type": "ValidationError",
  "error_message": "..."
}
```
This inconsistency makes it harder for agents to handle errors uniformly.

---

### 🐛 BUG #5 — `staytime_min` is always 0 even when items clearly have non-zero service times
**Severity: Low**

In the deterministic test (service time = 1.0 exactly), the server reports:
```json
"staytime_average": 1.0,
"staytime_max": 1.0,
"staytime_min": 0
```
`staytime_min = 0` when every single item has a service time of exactly 1.0 is incorrect. The minimum should also be 1.0. This suggests `staytime_min` is either not being tracked properly or is initialized to 0 and never updated for the first item.

---

## 3. RESPONSE FORMAT INCONSISTENCIES

### ⚠️ ISSUE #1 — `list_elements` and `list_connections` return multiple `TextContent` objects instead of a single JSON array
**Severity: Low-Medium**

`list_elements` returns **one `TextContent` per element** (4 separate text blocks for 4 elements), while `describe_model` returns a single unified JSON object containing all elements as an array. This is inconsistent. An agent parsing `list_elements` must handle a multi-part response, whereas `describe_model` gives a clean single JSON. Both tools should return a single JSON array.

Notably, `list_elements` does include a `structuredContent` field with the correct array format — but `list_connections` and other tools do not consistently provide `structuredContent`. This should be standardized.

---

### ⚠️ ISSUE #2 — `connect_batch` response includes full `current_model` snapshot (very verbose)
**Severity: Low**

Both `create_elements_batch` and `connect_batch` return the entire model snapshot in `current_model`. While useful for debugging, this makes responses very large. Consider making this optional (e.g., a `verbose` flag) or only returning a diff/summary.

---

## 4. DOCUMENTATION / TOOL DESCRIPTION ISSUES

### 📝 DOC ISSUE #1 — `run_experiment` status values are undocumented
The tool description mentions `status="wall_clock_timeout"` but does not enumerate **all possible status values**. Based on testing, at least these exist: `"completed"`, `"wall_clock_timeout"` (documented but broken — see Bug #2), `"network_idle"` (undocumented). All possible status values should be listed in the tool description.

---

### 📝 DOC ISSUE #2 — `triang` distribution's `c` parameter is confusing
The description says: *"Mode as a fraction of [loc, loc+scale]"*. This is technically correct (it's the scipy convention) but highly non-intuitive. Most users think of a triangular distribution in terms of `(min, mode, max)`. The documentation should add a concrete example, e.g.:
> *"For a triangle with min=2, mode=5, max=8: set loc=2, scale=6, c=0.5 (since (5-2)/6 = 0.5)"*

---

### 📝 DOC ISSUE #3 — `ItemsQueue` `capacity` field: behavior when full is undocumented
What happens when the queue reaches its capacity? Are items dropped? Does the source block? This is critical for model design and is not mentioned anywhere in the tool descriptions or schemas.

---

### 📝 DOC ISSUE #4 — `get_stats` description says it works in "READY" state but doesn't clarify stats are all zero
The description says *"Works in READY (stats are all 0 before a run)"* — this is actually correct and was confirmed in testing. However, it's buried in the description. It should be more prominent, as an agent might call `get_stats` before a run and be confused by all-zero results.

---

### 📝 DOC ISSUE #5 — `connect_batch` `strategy` field: what does `FirstAvailable` actually mean for a single destination?
The strategy is described but its semantics when there's only one destination are not explained. Does `FirstAvailable` vs `RoundRobin` matter with a single destination? (Answer: no, they're equivalent — but this should be stated.)

---

### 📝 DOC ISSUE #6 — No documentation on what `staytime_current` means
The stats include `staytime_current` but it's never defined. Based on testing, it appears to be the stay time of the **last item that passed through** (or the item currently in service). This should be explicitly documented.

---

### 📝 DOC ISSUE #7 — State machine transitions are documented but "completed → building" via `new_model` is missing
The `state_machine` in `get_supported_types` shows:
```
"any → building": "new_model"
```
This is correct but the word "any" is vague. It should explicitly say `"building | ready | completed → building"` to make it clear that `new_model` can be called at any point, including after a run.

---

## 5. WHAT WORKS WELL ✅

1. **Full happy-path workflow** works flawlessly: `new_model → create_elements_batch → connect_batch → initialize_model → run_experiment → get_stats`
2. **All 4 distribution types** (`expon`, `uniform`, `norm`, `triang`) are accepted and produce plausible results
3. **Multi-server parallelism** works correctly (RoundRobin split between `srv_a` and `srv_b` was ~50/50 as expected)
4. **State machine enforcement** is solid — trying to run before initializing, or running twice, gives clear error messages
5. **Partial success pattern** in batch operations is well-designed — the server stops at the first failure and reports exactly which element/connection failed and why
6. **Duplicate ID detection** works correctly
7. **Invalid connection targets** (nonexistent origin or destination) are caught with clear messages
8. **`describe_model`** provides a complete snapshot including `last_run_info` after a run — very useful
9. **`new_model` resets cleanly** from any state, including `completed`
10. **Simulation performance** is excellent — 10,000 time units with ~5,000 events runs in ~0.15 wall seconds

---

## 6. SUMMARY TABLE FOR CLAUDE CODE

| # | Type | Severity | Description |
|---|---|---|---|
| B1 | Bug | Medium | `InterArrivalSource` `content_current` = negative, `content_average` = -1.0 |
| B2 | Bug | Medium | Wall clock timeout returns `"network_idle"` instead of `"wall_clock_timeout"` |
| B3 | Bug | Low-Med | `Sink` `content_average` always = 1.0 (likely wrong) |
| B4 | Bug | Medium | Pydantic validation errors surface as raw MCP errors, not structured JSON |
| B5 | Bug | Low | `staytime_min` always = 0 even with deterministic non-zero service times |
| I1 | Inconsistency | Low-Med | `list_elements`/`list_connections` return multi-part responses vs single JSON |
| I2 | Inconsistency | Low | `create_elements_batch`/`connect_batch` return full model snapshot (verbose) |
| D1 | Docs | Medium | `run_experiment` status values not fully enumerated |
| D2 | Docs | Low-Med | `triang` `c` parameter needs a concrete example |
| D3 | Docs | Medium | Queue full behavior (blocking vs dropping) not documented |
| D4 | Docs | Low | `staytime_current` semantics not defined |
| D5 | Docs | Low | `FirstAvailable` vs `RoundRobin` with single destination not clarified |
| D6 | Docs | Low | `"any"` in state machine transitions should be explicit |