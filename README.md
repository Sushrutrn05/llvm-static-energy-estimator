# LLVM Static Energy Estimation Framework

A static analysis pass for LLVM 14 that estimates the relative energy consumption of C/C++ programs at the basic-block level. Uses block-frequency weighting, a JSON-driven energy cost model, and source-level heatmapping to identify energy hotspots and suggest compiler optimizations.

## Features

- **Per-function energy estimation** — weighted by LLVM's block frequency analysis (BFI)
- **Per-block breakdown** — energy per basic block with frequency normalization
- **Energy hotspots** — top-3 blocks ranked by energy contribution percentage
- **Optimization advisor** — rule-based suggestions for high mul/div/load/store/call density
- **Source code heatmap** — line-by-line energy coloring via DWARF debug info
- **JSON report** — machine-readable output for CI pipelines
- **HTML dashboard** — self-contained professional report with KPI cards, hotspot cards, advisor cards, and heatmap
- **Pluggable energy model** — JSON file maps LLVM opcodes to energy costs
- **LLVM optimization remarks** — integrates with `-pass-remarks-analysis=energy`

## Requirements

| Tool | Version |
|------|---------|
| LLVM | 14.x (clang++-14, opt-14, llvm-config-14) |
| C++ Standard | C++17 |
| Python | 3.8+ (for HTML dashboard only) |
| OS | Linux (tested on Ubuntu 22.04 WSL) |

## Installation

```bash
# Install LLVM 14 (Ubuntu 22.04)
wget https://apt.llvm.org/llvm.sh
chmod +x llvm.sh
sudo ./llvm.sh 14

# Verify installation
clang++-14 --version
llvm-config-14 --version
```

## Build

```bash
# Build the shared library
./scripts/build.sh

# Or manually:
clang++-14 $(llvm-config-14 --cxxflags) -fPIC -std=c++17 \
    EnergyPass.cpp \
    $(llvm-config-14 --ldflags) --shared \
    -o EnergyPass.so
```

## Quick Start

```bash
# Compile a C file to LLVM IR with debug info
clang-14 -S -emit-llvm -g test.c -o test.ll

# Run the energy pass
opt-14 -load ./EnergyPass.so -enable-new-pm=0 -energy \
    -energy-model models/x86_energy.json \
    -energy-report reports/energy_report.json \
    -pass-remarks-analysis=energy -disable-output test.ll

# Generate HTML dashboard
python3 scripts/visualize.py

# Open the report
open reports/energy_report.html
```

## Usage

```bash
# Using the run script
./scripts/run.sh test.c

# With custom optimization level
./scripts/run.sh benchmarks/matrix.c -O0

# Run on all benchmarks
./scripts/run_benchmarks.sh

# Generate JSON report with custom path
opt-14 -load ./EnergyPass.so -enable-new-pm=0 -energy \
    -energy-model models/x86_energy.json \
    -energy-report my_report.json \
    -disable-output my_program.ll
```

### Command-Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `-energy-model` | `models/x86_energy.json` | Path to JSON energy cost model |
| `-energy-report` | `reports/energy_report.json` | Path for JSON report output |
| `-pass-remarks-analysis=energy` | — | Enable LLVM optimization remarks |

## Example Output

### Terminal (abbreviated)

```
===== ENERGY HOTSPOTS =====
Rank  Block                        Energy    Percent
----  -------------------------  --------  --------
   1  BB_2                       620.00    53.91%
   2  BB_1                       256.00    22.26%
   3  BB_3                       248.00    21.57%

  Optimization Advisory:
  ---------------------------------------------------------------------
  Observation:   46.43% memory ops (cost: 39.00)
  Recommendation: Improve data reuse via tiling or loop interchange
  Benefit:       Fewer cache misses reduces DRAM access energy
  ---------------------------------------------------------------------
```

### Optimization Remarks

```
remark: test.c:7:21: block energy: 256.00 (frequency: 32.00)
remark: test.c:5:0: estimated energy: 1150.00 (28 insts, 5 blocks)
```

## Energy Model

The file `models/x86_energy.json` maps LLVM IR opcodes to relative energy costs normalized to `add = 1.0`. Values are derived from published instruction-level power analysis (Tiwari et al., 1994; Intel Optimization Manual).

Key costs:
- `add`/`sub`: 1.0
- `mul`: 3.0 | `div`: 6.0
- `load`/`store`: 3.0
- `call`: 3.0
- `phi`/`bitcast`: 0.5 (no machine cost)

## Project Structure

```
llvm-energy/
├── EnergyPass.cpp            # Main LLVM pass implementation
├── EnergyPass.so             # Compiled shared library (generated)
├── test.c                    # Simple test program
├── test.ll                   # Compiled IR (generated)
├── models/
│   └── x86_energy.json       # Energy cost model (41 opcodes)
├── benchmarks/
│   ├── loop.c                # Arithmetic-intensive tight loop
│   ├── matrix.c              # 64×64 integer matrix multiply
│   └── memory.c              # Linked-list traversal
├── scripts/
│   ├── build.sh              # Build the pass
│   ├── run.sh                # Compile + run on a source file
│   ├── visualize.py          # HTML dashboard generator
│   ├── compile_benchmarks.sh # Compile all benchmarks
│   └── run_benchmarks.sh     # Run pass on all benchmarks
├── reports/
│   ├── energy_report.json    # Generated JSON report
│   ├── energy_report.html    # Generated HTML dashboard
│   └── validation.md         # Academic validation report
├── charts/                   # Generated chart images (optional)
├── README.md
├── DESIGN.md
├── IMPLEMENTATION.md
└── EVALUATION.md
```

## Related Work

- **Tiwari et al. (1994)** — "Power Analysis of Embedded Software" — foundational instruction-level energy measurement methodology
- **Sinha & Chandrakasan (2001)** — "Energy Aware Software" — comprehensive survey of instruction energy
- **Intel 64 and IA-32 Optimization Reference Manual** — published instruction latencies and power characteristics

## License

MIT
