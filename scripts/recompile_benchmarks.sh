#!/bin/bash
cd /mnt/c/Users/91636/llvm-energy
for f in benchmarks/loop benchmarks/matrix benchmarks/memory benchmarks/recursion benchmarks/sorting; do
    echo "=== Compiling ${f}.c ==="
    clang-14 -S -emit-llvm -O0 -g "${f}.c" -o "${f}.ll"
done
echo "All recompiled"
