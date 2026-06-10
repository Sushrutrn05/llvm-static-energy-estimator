# Implementation Guide

## LLVM APIs Used

| API | Header | Purpose |
|-----|--------|---------|
| `FunctionPass` | `llvm/Pass.h` | Base class for the pass |
| `BlockFrequencyInfoWrapperPass` | `llvm/Analysis/BlockFrequencyInfo.h` | Block execution frequency |
| `json::parse` | `llvm/Support/JSON.h` | Parse cost model JSON |
| `raw_fd_ostream` | `llvm/Support/FileOutput.h` | Write JSON report |
| `Instruction::getOpcodeName` | `llvm/IR/Instruction.h` | Get opcode string |
| `DebugLoc` | `llvm/IR/DebugLoc.h` | Source line mapping |

Analysis dependencies: `BlockFrequencyInfoWrapperPass`, `BranchProbabilityInfoWrapperPass`,
`LoopInfoWrapperPass`, `OptimizationRemarkEmitterWrapperPass`.

## OptimizationRemarkEmitter Integration

The pass emits per-block and per-function remarks through LLVM's
`OptimizationRemarkAnalysis` system. Remarks extract source locations
automatically from the instruction's `DebugLoc` metadata.

```cpp
// Per-block remark with source location
OptimizationRemarkEmitter &ORE =
    getAnalysis<OptimizationRemarkEmitterWrapperPass>().getORE();
OptimizationRemarkAnalysis Rem("energy", "BlockEnergy", &*BB.begin());
Rem << "block energy: " << fmtDouble(BlockEnergy)
    << " (frequency: " << fmtDouble(NormalizedFreq) << ")";
if (DebugLoc DL = Inst.getDebugLoc())
    Rem << " at " << DL->getFilename() << ":" << DL->getLine();
ORE.emit(Rem);
```

Enable with `-pass-remarks-analysis=energy` (or `-Rpass-analysis=energy` via
clang). Remarks are visible as:

```
file.c:line:0: remark: energy: block energy: 620.00 (frequency: 1000.00) at file.c:7 [-Rpass-analysis=energy]
```

## Pass Lifecycle

- `doInitialization`: Load JSON energy model into `unordered_map<string,double>`
- `runOnFunction` (per function):
  1. Get BFI and ORE analyses
  2. For each basic block:
     - Get normalized frequency from BFI
     - For each instruction:
       - Lookup opcode cost (default 1.0 if missing)
       - Accumulate block energy: `cost × frequency`
       - Count opcode types for breakdown
       - Accumulate source-line energy via `DebugLoc`
     - Store `BlockReport`
     - Emit per-block optimization remark
  3. Compute top-3 hotspots by energy
  4. Generate advisories from opcode percentages
  5. Print instruction breakdown table
  6. Return `false` (read-only pass)
- `doFinalization`: Serialize reports to JSON via `raw_fd_ostream`

## Build and Execution

1. Compile to LLVM IR:
   ```
   clang-14 -S -emit-llvm -g -O0 test.c -o test.ll
   ```
2. Run the pass:
   ```
   opt-14 -load ./EnergyPass.so -energy \
       -energy-model models/x86_energy.json \
       -energy-report reports/energy_report.json \
       -disable-output test.ll
   ```
3. Generate HTML report:
   ```
   python3 scripts/visualize.py
   ```

Command-line options:
- `-energy-model <path>` (default: `models/x86_energy.json`)
- `-energy-report <path>` (default: `reports/energy_report.json`)
- `-pass-remarks-analysis=energy` (enables remarks)

## Data Structures

```cpp
struct BlockReport {
    std::string Name;     // e.g., "BB_0"
    double Frequency;     // Normalized block frequency
    double Energy;        // Σ(cost × frequency) for block
};

struct FuncReport {
    std::string Name;
    double TotalEnergy;
    std::vector<BlockReport> Blocks;
    std::vector<HotspotReport> Hotspots;   // top 3 by energy
    std::vector<AdvisoryReport> Advisories;
    std::string SourceFile;
    std::vector<SourceLineEnergy> SourceLines;
};
```

## Block Frequency Analysis (BFI) Integration

BFI provides estimated execution counts. Normalized frequency:
```cpp
double NormalizedFreq = (double)BFI.getBlockFreq(&BB).getFrequency()
                      / (double)BFI.getEntryFreq();
```
Energy per instruction: `cost × NormalizedFreq`.

## Energy Model Implementation

JSON file maps LLVM opcode names to relative costs. Loaded once in
`doInitialization()`:

```cpp
auto Buffer = MemoryBuffer::getFile(ModelPath);
auto Json = json::parse(Buffer->get()->getMemBufferRef());
// Populate unordered_map<string,double> from Json
```

Example model:
```json
{"add": 1.0, "mul": 3.0, "load": 3.0, "store": 3.0, "call": 3.0, "phi": 0.5}
```
Cost lookup: `OpcodeEnergy[I.getOpcodeName()]` (defaults to 1.0).

## JSON Report Generation

`doFinalization` writes JSON report:
```json
{
  "functions": [{
    "name": "compute",
    "total_energy": 1150.0,
    "blocks": [
      {"name": "entry", "frequency": 1.0, "energy": 50.0},
      {"name": "BB_1", "frequency": 1000.0, "energy": 1100.0}
    ],
    "hotspots": [{"name": "BB_1", "energy": 1100.0, "percent": 95.6}],
    "advisories": [],
    "source_lines": [
      {"line": 7, "energy": 500.0},
      {"line": 8, "energy": 600.0}
    ]
  }]
}
```
Written via `raw_fd_ostream`.

## HTML Visualization

Python script `scripts/visualize.py` reads JSON report and generates
self-contained HTML with:
- Function summary table
- Block-level detail
- Hotspot ranking (top 3)
- Optimization advisories
- Source code heatmap (green→red scale via `DebugLoc` line numbers)

## Optimization Advisor

Rule-based thresholds on instruction mix percentages:

| Pattern | Threshold | Suggestion |
|---------|-----------|------------|
| `mul`/`fmul` | ≥8% | Vectorization or strength reduction |
| `sdiv`/`udiv`/`fdiv` | ≥5% | Multiply-by-inverse |
| `load` | ≥30% | Improve cache locality |
| `store` | ≥20% | Reduce memory writes |
| `load` + `store` | ≥40% | Tiling / data reuse |
| `call` | ≥20% | Consider inlining |

Each advisory: observation (%), recommendation, potential benefit.
