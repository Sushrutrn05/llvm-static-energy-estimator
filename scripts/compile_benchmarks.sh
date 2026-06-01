#!/bin/bash
cd /mnt/c/Users/91636/llvm-energy
for f in benchmarks/loop benchmarks/matrix benchmarks/memory; do
    echo "=== Compiling ${f}.c ==="
    clang-14 -S -emit-llvm -O1 -g "${f}.c" -o "${f}.ll"
done
echo "All compiled"
