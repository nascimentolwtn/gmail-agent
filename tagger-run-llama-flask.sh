#!/bin/bash
set -e

echo "🚀 Starting Gmail Tagger Stack (Qwen2.5 + Flask)"
echo ""

# Kill any existing processes on port 11434 or 5050
cleanup() {
  echo ""
  echo "⏹️  Shutting down..."
  pkill -f "llama-server" 2>/dev/null || true
  pkill -f "tagger_flask.py" 2>/dev/null || true
}
trap cleanup EXIT

# Start llama-server in background
echo "📦 Starting Qwen2.5 LLM server on port 11434..."
/home/lw_na/llama.cpp/build/bin/llama-server \
  --model /home/lw_na/models-llm/Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf \
  --host 0.0.0.0 --port 11434 \
  --n-gpu-layers 99 --ctx-size 8192 --keep 1024 \
  --jinja --flash-attn on \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --parallel 1 --threads 4 \
  --temp 1.0 --top-k 20 --top-p 0.95 \
  --presence-penalty 1.5 --repeat-penalty 1.05 \
  --reasoning off \
  > /tmp/llama-server.log | tee /home/lw_na/llama.cpp/build/bin/llama-server.log &

LLAMA_PID=$!
echo "✓ LLM server PID: $LLAMA_PID"

echo "⏳ LLM server is comming up..."

# Start Flask app
echo ""
echo "🌐 Starting Flask app on http://0.0.0.0:5050..."
cd /home/lw_na/git/gmail-agent/
python tagger_flask.py
