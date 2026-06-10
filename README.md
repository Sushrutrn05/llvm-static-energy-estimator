# LLVM Static Energy Estimator

## Overview

An LLVM 14 pass that estimates relative energy consumption of C programs at the basic-block level. Uses block frequency analysis (BFI) to weight instruction costs. Outputs terminal tables, JSON reports, and an HTML source heatmap.

Architecture: A FunctionPass reads LLVM IR with debug info, queries BFI for block frequencies, looks up opcode costs from a JSON model, and outputs terminal/JSON reports. LLVM remarks are emitted via OptimizationRemarkAnalysis. A separate Python script generates the HTML heatmap.

## Features

- Function-wise energy estimation
- Basic-block hotspot detection
- JSON report generation
- HTML visualization
- Optimization suggestions
- LLVM remark integration (`-Rpass-analysis=energy`)
- Built-in x86-64 and AArch64 energy models (`models/x86_energy.json`, `models/aarch64_energy.json`)

## Requirements

- LLVM 14
- C++17
- Python 3

## Build

```
./scripts/build.sh
```

Produces `EnergyPass.so`.

## Run

```
./scripts/run.sh test.c
```

## Sample Output

```
===== ENERGY HOTSPOTS =====
Rank  Block                        Energy    Percent
----  -------------------------  --------  --------
    1  BB_2                       620.00    53.91%
    2  BB_1                       256.00    22.26%
    3  BB_3                       248.00    21.57%
```

## Generate HTML Report

After running the pass and generating the JSON report, create the visualization:

```
python3 scripts/visualize.py
```

This produces `reports/energy_report.html` with a source code heatmap.

## Remarks via -Rpass-analysis=energy

The pass emits per-block and per-function remarks through LLVM's
OptimizationRemarkAnalysis system. Enable them with:

```
opt-14 -load ./EnergyPass.so -energy -pass-remarks-analysis=energy \
    -energy-model models/x86_energy.json -disable-output test.ll
```

Remarks include source file and line information when debug info is present
(`-g` flag). Example output:

```
benchmarks/loop.c:8:0: remark: energy: block energy: 22.00 (frequency: 1.00) at loop.c:8 [-Rpass-analysis=energy]
benchmarks/loop.c:9:0: remark: energy: block energy: 256.00 (frequency: 32.00) at loop.c:9 [-Rpass-analysis=energy]
benchmarks/loop.c:10:0: remark: energy: block energy: 620.00 (frequency: 31.00) at loop.c:10 [-Rpass-analysis=energy]
benchmarks/loop.c:12:0: remark: energy: estimated energy: 1158.00 (32 insts, 5 blocks) [-Rpass-analysis=energy]
```

This integrates with clang's `-Rpass-analysis=energy` when used in a full
compilation pipeline. `scripts/run.sh` enables this automatically.

## Project Structure

```
llvm-energy/
├── EnergyPass.cpp            # LLVM pass implementation
├── models/
│   ├── x86_energy.json        # x86-64 cost model (41 opcodes)
│   └── aarch64_energy.json    # AArch64 cost model (41 opcodes, Cortex-A55)
├── benchmarks/
│   ├── loop.c                # Arithmetic tight loop
│   ├── matrix.c              # 64×64 matrix multiply
│   ├── memory.c              # Linked-list traversal
│   ├── recursion.c           # Recursive factorial
│   └── sorting.c             # Bubble sort array
├── scripts/
│   ├── build.sh              # Build the pass
│   ├── run.sh                # Compile + run on source file
│   ├── visualize.py          # HTML report generator
│   └── run_benchmarks.sh     # Run all benchmarks
├── README.md
├── DESIGN.md
├── IMPLEMENTATION.md
└── EVALUATION.md
```

## Limitations

- Uses a static energy model
- Estimates relative energy only
- Not validated using physical power measurements
