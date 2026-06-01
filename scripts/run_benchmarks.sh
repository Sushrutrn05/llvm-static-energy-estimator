#!/bin/bash
cd /mnt/c/Users/91636/llvm-energy
MODEL=models/x86_energy.json
PASS=./EnergyPass.so
for name in loop matrix memory; do
    echo "============================================================"
    echo "  BENCHMARK: ${name}"
    echo "============================================================"
    opt-14 -load "$PASS" -enable-new-pm=0 -energy \
        -energy-model "$MODEL" -disable-output "benchmarks/${name}.ll" 2>/dev/null
    echo ""
done
