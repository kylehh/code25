---
title: "Priority Scheduling on Dynamo + vLLM: Three Things That Have to Be True"
mathjax: true
toc: true
categories:
  - Study
tags:
  - Dynamo
  - vLLM
  - Scheduling
  - Benchmark
---

Short reference for "the next time I touch Dynamo + vLLM priority." Long
version lives in the project `README.md`; raw numbers are in
`results/ttft_by_priority.md`. This post distills the three preconditions
that have to hold simultaneously, the surprising direction convention, and
the triage checklist for when the resulting TTFT-by-priority table comes out
flat.

## 1 The three things that have to be true

To see a priority-scheduling effect in a TTFT benchmark against
`dynamo.vllm`, **all three** must hold:

1. **Field path.** The trace row's priority must live at
   `extra.nvext.agent_hints.priority`. Anything else (e.g.
   `extra.nvext.priority`) is silently dropped by the Dynamo handler.
2. **Scheduler policy.** `dynamo.vllm` defaults to FCFS. Pass
   `--scheduling-policy priority` on **both** decode and prefill workers.
3. **Real queueing.** The number of in-flight requests must exceed
   `max_num_seqs`. Otherwise everything fits in the running batch and the
   scheduler has no admission decisions to make.

Drop any one of these → flat TTFT, looks like priority is broken.

## 2 Direction (still surprising)

In vLLM's `priority` policy, **lower numeric value = higher priority**.
`p0` finishes first, `p64` finishes last. This is the opposite of what most
callers expect from an `nvext.priority` field.

`priority_sweep.py` carries a comment claiming Dynamo's handler negates the
value before passing it to vLLM. On the build path I tested
(`vllm-runtime:1.0.1-efa-amd64`, Dynamo platform 1.1.1), it does not — the
raw value reaches vLLM. Either fix the handler upstream or invert the
values you send.

This is the single biggest source of "priority looks broken" reports. If
your high-priority class has a *larger* number, you are demoting it.

## 3 The knobs I actually used

| Knob | Final value | Notes |
|---|---|---|
| Model | `Qwen/Qwen3-32B` | one decode + one prefill, `g7e.12xlarge` on EKS |
| `max_num_seqs` | 64 | small enough that 1005 requests queue |
| Scheduling policy | `priority` | the default FCFS doesn't sort by priority |
| Trace size | 1005 requests, all `timestamp=0` | one big burst at t=0 |
| Output length | 310 tokens, fixed | per-trace `output_length` |
| aiperf mode | `mooncake_trace` + `--fixed-schedule` | replay as-is, no closed-loop concurrency |
| Streaming | required | so aiperf can measure TTFT |

The burst-at-t=0 design is deliberate: every request enters the queue
simultaneously, so the only thing that can reorder them is the scheduler.
That makes the priority gradient cleanly readable instead of mixed with
arrival timing.

## 4 The benchmark, in one block

```bash
# 1. Deploy priority-aware backend
kubectl -n dynamo-system apply -f manifests/disagg_s64.yaml

# 2. Port-forward
kubectl -n dynamo-system port-forward svc/vllm-disagg-frontend 8000:8000

# 3. Replay
aiperf profile \
  --model Qwen/Qwen3-32B \
  --endpoint-type chat \
  --streaming \
  --url localhost:8000 \
  --input-file tracex5_burst.jsonl \
  --custom-dataset-type mooncake_trace \
  --fixed-schedule

# 4. Analyze
python3 scripts/ttft_stats.py
```

`--fixed-schedule` tells aiperf to replay the trace exactly as-is — no
closed-loop concurrency, no arrival regulation. Combined with all
timestamps at `0`, this gives you a single thunderclap burst that exposes
the scheduler.

## 5 Quick triage when the table comes out flat

In rough order of frequency:

1. **Field path.**
   `head -1 trace.jsonl | python3 -m json.tool` — confirm priority is at
   `extra.nvext.agent_hints.priority`, not `extra.nvext.priority`.

2. **Policy actually applied.**
   `kubectl logs <vllm-pod> | grep -iE "Scheduler config|scheduling.policy"`
   — confirm the priority policy made it onto the worker. If you see
   `fcfs` or no `scheduling-policy` line, your manifest didn't take effect.

3. **Not enough load.**
   TTFT mean ≤ a few seconds → no real queueing. Either drop `max_num_seqs`
   or grow the burst. Rule of thumb: pick `max_num_seqs` so that
   `requests_in_burst / max_num_seqs >= ~15`, otherwise you only get a few
   scheduler decisions to sort over.

4. **First-batch admission is FCFS.**
   The very first batch of `max_num_seqs` requests admits in arrival order
   regardless of priority — visible as anomalously low `min` for mid-tier
   priorities. Not a bug; just don't read too much into per-priority `min`.

5. **Session ID drift.**
   `conversation_id` must contain `-pXX`. If `ttft_stats.py` reports
   `unmatched > 0`, your trace's `session_id` format drifted from what the
   stats script expects.

## 6 Why the original closed-loop sweep didn't show this

Closed-loop `priority_sweep.py` keeps `concurrency` slots in flight and
refills as responses come back. Whether it produces a priority gradient
depends on whether `concurrency > max_num_seqs` (queue exists) **and** the
scheduling policy is actually `priority`. In the original sweep, one or
both of those held by accident, but the gradient was harder to read because
the arrival pattern wasn't a clean burst — closed-loop refilling
interleaves new arrivals with completions, smearing the signal.

Replaying through aiperf with `tracex5_burst.jsonl` + `disagg_s64.yaml` is
the controlled version: pure open-loop, all arrivals at t=0, priority is
the only variable the scheduler can act on.

## 7 Takeaway

Three independent moving pieces — field path, scheduler policy, queue
pressure — all have to align for priority scheduling to be visible. Each
of them fails silently:

- Wrong field path → request accepted, priority dropped
- Wrong policy → request accepted, sorted FCFS anyway
- No queueing → request accepted, runs immediately regardless of priority

Combined with the inverted direction convention (lower = higher priority,
*not* negated by the handler on at least one build path), it's easy to set
up a benchmark that "works" — admits requests, returns tokens, produces a
results table — and shows zero signal.

The controlled version is small: a burst trace with `timestamp=0`,
`max_num_seqs=64`, `--scheduling-policy priority` on both workers,
priority encoded at `extra.nvext.agent_hints.priority`, replayed with
`aiperf --fixed-schedule`. Anything looser than that and you're measuring
something other than the policy.

## See also

- `../README.md` — full journey and reproduction steps
- `../results/ttft_by_priority.md` — phase-by-phase tables
- `../manifests/disagg.yaml` vs `disagg_s64.yaml` — minimal diff is two
  flags on each worker: `--max-num-seqs 64` and `--scheduling-policy priority`
- `../scripts/build_trace.py` — where the correct field path is encoded
- `/home/khuang/_research/local_priority_sch/` — upstream closed-loop sweep
