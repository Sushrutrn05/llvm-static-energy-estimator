#!/bin/bash
# Run the LLVM EnergyPass on a C source file.
# Usage:
#   ./scripts/run.sh test.c
#   ./scripts/run.sh benchmarks/loop.c
#   ./scripts/run.sh benchmarks/matrix.c -O0
#
# The script compiles the source to LLVM IR with debug info,
# then runs the EnergyPass with the x86 energy model.

set -euo pipefail

SRC="${1:?Usage: $0 <source.c> [clang-flags]}"
shift 1
CLANG_FLAGS="${*:--O1}"
BASE="${SRC%.c}"
LL="${BASE}.ll"
MODEL="models/x86_energy.json"
PASS="./EnergyPass.so"

if [ ! -f "$PASS" ]; then
    echo "[ERROR] EnergyPass.so not found. Run ./scripts/build.sh first."
    exit 1
fi

echo "[*] Compiling ${SRC} -> ${LL} (${CLANG_FLAGS}) ..."
clang-14 -S -emit-llvm -g $CLANG_FLAGS "$SRC" -o "$LL"

echo "[*] Running EnergyPass ..."
opt-14 -load "$PASS" -enable-new-pm=0 -energy \
    -energy-model "$MODEL" -disable-output "$LL" 2>&1 | grep -v "^$"

echo "[*] Done"
