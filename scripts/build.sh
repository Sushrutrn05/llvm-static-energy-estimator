#!/bin/bash
# Build the LLVM EnergyPass shared library.
# Requires: LLVM 14 (clang++-14, llvm-config-14)
#
# Usage:
#   ./scripts/build.sh

set -euo pipefail

LLVM_CXXFLAGS=$(llvm-config-14 --cxxflags)
LLVM_LDFLAGS=$(llvm-config-14 --ldflags)

echo "[*] Building EnergyPass.so ..."
clang++-14 $LLVM_CXXFLAGS -fPIC -std=c++17 \
    EnergyPass.cpp \
    $LLVM_LDFLAGS --shared \
    -o EnergyPass.so

echo "[OK] EnergyPass.so created"
