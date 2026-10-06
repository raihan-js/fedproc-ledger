#!/usr/bin/env bash
# Start the bundled llama.cpp server on an Ollama GGUF blob with 4 parallel slots (Ollama cannot batch qwen3.5).
# usage: scripts/llama_server.sh 9b|4b [port]   (stop it by PID; it prints the PID file path)
set -euo pipefail
size="${1:?9b or 4b}"; port="${2:-11600}"
case "$size" in
  9b) blob=sha256-dec52a44569a2a25341c4e4d3fee25846eed4f6f0b936278e3a3c900bb99d37c ;;
  4b) blob=sha256-81fb60c7daa80fc1123380b98970b320ae233409f0f71a72ed7b9b0d62f40490 ;;
  *) echo "9b or 4b"; exit 2 ;;
esac
L="$HOME/.local/ollama/lib/ollama"
mkdir -p data/logs
GGML_BACKEND_PATH="$L/cuda_v13/libggml-cuda.so" LD_LIBRARY_PATH="$L:$L/cuda_v13" \
  nohup "$L/llama-server" -m "$HOME/.ollama/models/blobs/$blob" -ngl 99 -c 32768 -np 4 -fa on -ctk q8_0 -ctv q8_0 \
  --host 127.0.0.1 --port "$port" --jinja --chat-template-kwargs '{"enable_thinking": false}' \
  > "data/logs/llama_server_$size.log" 2>&1 &
echo $! > "data/logs/llama_server_$size.pid"; echo "pid $(cat data/logs/llama_server_$size.pid), log data/logs/llama_server_$size.log"
