# Model routing and costs - measurements, 11 Nov 2026

## Local model benchmark (F10, measured on the production server)

Server: InterServer VPS, 4 shared cores, 15 GB memory, no GPU. Runtime: Ollama in a container limited to 3 CPUs and
6 GB, one request at a time. Task: classify one tender title into five classes, one-word answer. Script:
deploy/ops/bench-llm.sh (run through the server-ops workflow).

| Model | Generation speed | Time per classification | Memory | Answer |
|---|---|---|---|---|
| qwen3:0.6b | about 18.5 tokens/s | 10 to 11.5 s | 1.2 GB | not captured in this run |
| qwen3:1.7b | about 7.8 tokens/s | 31 to 39 s | 3.1 GB | "fertilizer" (correct) in 2 of 2 captured |

Host load average during the run: 3.8 on 4 cores, so local inference competes directly with the collectors.

## Decision for this release

- Tier 0 (code) stays the default for units, dates, matching gates, cash flows and permissions.
- Local models are NOT switched on in production: at 10 to 35 seconds per item and near-full CPU they would slow
  collection, and accuracy of the 0.6b model is unmeasured. They remain available for a night-time batch experiment.
- Tier 2 and 3 stay on the Anthropic API (lib/anthropic.ts). No OpenAI adapter exists.
- Not claimed: any cost saving from local models.

## Still open

- A router module that records tier, latency and cost per call, and a hard daily spend stop (today the daily budget
  is an alert only, lib/anthropic.ts).
- A labelled validation set for the small-model tasks.
