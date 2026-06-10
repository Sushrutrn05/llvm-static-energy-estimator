#!/bin/bash
cd /mnt/c/Users/91636/llvm-energy
for b in loop matrix memory recursion sorting; do
    echo "========== $b =========="
    opt-14 -load ./EnergyPass.so -enable-new-pm=0 -energy \
        -energy-model models/x86_energy.json \
        -pass-remarks-analysis=energy \
        -disable-output "benchmarks/${b}.ll" 2>&1
    echo ""
done
