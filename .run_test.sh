#!/bin/bash
set -e
cd /Users/teamgrit/Documents/CoWater

pkill -f "server/system-agent/system_agent.py" 2>/dev/null || true
sleep 1

mkdir -p .logs
nohup .venv/bin/python server/system-agent/system_agent.py > .logs/System-Agent.log 2>&1 &
SA_PID=$!
echo "System Agent PID: $SA_PID"

for i in {1..30}; do
  curl -sf http://127.0.0.1:9116/health >/dev/null && echo "System Agent ready" && break
  sleep 1
done

echo ""
echo "========== RUN 1 =========="
PYTHONUNBUFFERED=1 .venv/bin/python docs/run_mine_removal_scenario.py

echo ""
echo "-- Restarting System Agent before RUN 2 --"
pkill -f "server/system-agent/system_agent.py" 2>/dev/null || true
sleep 2
nohup .venv/bin/python server/system-agent/system_agent.py > .logs/System-Agent.log 2>&1 &
echo "New System Agent PID: $!"
for i in {1..30}; do
  curl -sf http://127.0.0.1:9116/health >/dev/null && echo "System Agent ready" && break
  sleep 1
done

echo ""
echo "========== RUN 2 =========="
PYTHONUNBUFFERED=1 .venv/bin/python docs/run_mine_removal_scenario.py

echo ""
echo "All runs complete."
