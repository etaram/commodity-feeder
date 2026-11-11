#!/usr/bin/env bash
# Measures small local models on this server: speed and memory, one request at a time. Container is limited to
# 3 CPUs and 6 GB so the collectors and the database keep headroom. Removes nothing; stops the container at the end.
set -uo pipefail
docker rm -f ollama-bench >/dev/null 2>&1
docker run -d --name ollama-bench --cpus 3 --memory 6g -v ollama:/root/.ollama ollama/ollama >/dev/null
sleep 6
P='Classify this tender title into one of: fertilizer, generator, membrane, vehicle, other. Answer with one word. Title: Supply of 5,000 t granular urea 46% N in 50 kg bags'
for m in qwen3:0.6b qwen3:1.7b; do
  echo "== $m"; t0=$(date +%s)
  docker exec ollama-bench ollama pull "$m" >/dev/null 2>&1 && echo "pulled in $(( $(date +%s)-t0 ))s" || { echo "pull failed"; continue; }
  docker exec ollama-bench ollama run "$m" "hi" >/dev/null 2>&1   # warm up
  for i in 1 2 3; do
    docker exec ollama-bench ollama run "$m" --verbose "$P /no_think" 2>&1 | grep -vE "^\s*$|<think>|</think>" | grep -E "eval rate|total duration|^[A-Za-z]+\.?$" | tr '\n' ';'; echo
  done
  docker stats --no-stream --format 'memory {{.MemUsage}} cpu {{.CPUPerc}}' ollama-bench
done
echo "== host while loaded"; free -h | sed -n 2p; uptime
docker stop ollama-bench >/dev/null; docker rm ollama-bench >/dev/null; echo "bench container removed (model files kept in the ollama volume)"
