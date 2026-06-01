# Implementation Guide

## LLVM Pass Architecture

`EnergyPass` is an LLVM `FunctionPass` (legacy pass manager) registered via `RegisterPass<EnergyPass>`. It processes each function in the module independently, accumulating per-function data into a `FuncReport` struct, and emits aggregated results in `doFinalization()`.

### Pass Lifecycle

```
doInitialization(Module&)
  └── Load energy model JSON (once)
       └── Parse with llvm::json::parse()
            └── Populate OpcodeEnergy map

runOnFunction(Function&)          ← called for each function
  ├── Get analysis passes (BFI, ORE)
  ├── Iterate basic blocks
  │    ├── Get block frequency from BFI
  │    ├── Iterate instructions
  │    │    ├── Lookup opcode cost in OpcodeEnergy map
  │    │    ├── Accumulate block energy (cost × frequency)
  │    │    ├── Accumulate opcode statistics
  │    │    └── Accumulate source line energy (via DebugLoc)
  │    ├── Store BlockReport
  │    └── Emit per-block optimization remark
  ├── Compute hotspots (top 3 by energy)
  ├── Generate optimization advisories
  ├── Emit per-function optimization remark
  ├── Print instruction breakdown table
  └── Return false (module not modified)

doFinalization(Module&)
  └── Serialize AllReports to JSON
       └── Write via raw_fd_ostream
```

### Key Data Structures

```cpp
struct BlockReport {
    std::string Name;      // BB_0, BB_1, ... or LLVM block name
    double Frequency;       // Normalized block execution frequency
    double Energy;          // Weighted block energy
};

struct FuncReport {
    std::string Name;
    double TotalEnergy;
    std::vector<BlockReport> Blocks;
    std::vector<HotspotReport> Hotspots;
    std::vector<AdvisoryReport> Advisories;
    std::string SourceFile;
    std::vector<SourceLineEnergy> SourceLines;
};
```

## BlockFrequencyInfo Usage

`BlockFrequencyInfo` (BFI) provides static estimates of basic block execution frequencies using branch probabilities and loop trip counts.

### How It Works

1. The pass requires BFI via `AU.addRequired<BlockFrequencyInfoWrapperPass>()`
2. In `runOnFunction()`, BFI is retrieved:
   ```cpp
   BlockFrequencyInfo &BFI =
       getAnalysis<BlockFrequencyInfoWrapperPass>().getBFI();
   ```
3. For each block, the raw frequency and entry frequency are obtained:
   ```cpp
   uint64_t Freq = BFI.getBlockFreq(&BB).getFrequency();
   uint64_t EntryFreq = BFI.getEntryFreq();
   double NormalizedFreq = (double)Freq / EntryFreq;
   ```
4. Each instruction's energy contribution is `cost × NormalizedFreq`

### Trip Count Integration

BFI works with `LoopInfo` to compute loop trip counts. For a loop that iterates 1000 times:
- The loop header's frequency will be approximately 1000× the preheader's frequency
- Inner loop bodies get proportionally higher frequencies
- BFI integrates with `BranchProbabilityInfo` for conditional branches

## OptimizationRemarkEmitter Usage

The pass emits LLVM optimization remarks for integration with `-pass-remarks-analysis=energy`.

### Per-Block Remarks

```cpp
OptimizationRemarkEmitter &ORE =
    getAnalysis<OptimizationRemarkEmitterWrapperPass>().getORE();

const Instruction *First = &*BB.begin();
OptimizationRemarkAnalysis RemB("energy", "BlockEnergy", First);
RemB << "block energy: " << fmtDouble(BlockEnergy)
     << " (frequency: " << fmtDouble(NormalizedFreq) << ")";
ORE.emit(RemB);
```

### Per-Function Remarks

```cpp
OptimizationRemarkAnalysis Rem("energy", "EstimatedEnergy", &F);
Rem << "estimated energy: " << fmtDouble(TotalEnergy)
    << " (" << TotalInsts << " insts, "
    << TotalBlocks << " blocks)";
ORE.emit(Rem);
```

The 3-argument constructor `(PassName, RemarkName, Function*/Instruction*)` automatically extracts `DebugLoc` from the IR object's subprogram/instruction metadata, so source locations appear in the remark output without manual `DiagnosticLocation` construction.

## Energy Model Loading

The energy model is a JSON file loaded once in `doInitialization()`.

### JSON Format

```json
{
    "add": 1.0,
    "mul": 3.0,
    "load": 3.0,
    "store": 3.0,
    "call": 3.0,
    "phi": 0.5,
    ...
}
```

### Loading Process

1. `MemoryBuffer::getFile(Path)` — reads the entire file
2. `json::parse(Content)` — parses into a `json::Value` tree
3. Iterate key-value pairs, extract cost via `getAsNumber()`
4. Store in `std::unordered_map<std::string, double>`
5. On failure, fall back to default cost of 1.0 for all opcodes

### Opcode Lookup

```cpp
StringRef OpName = Inst.getOpcodeName();
auto It = OpcodeEnergy.find(OpName.str());
double Cost = (It != OpcodeEnergy.end()) ? It->second : 1.0;
```

If an opcode is missing from the model, a default cost of 1.0 is used. This ensures the pass never crashes on unexpected opcodes.

## Hotspot Analysis

After computing per-block energy, hotspots are identified by sorting blocks by descending energy:

```cpp
struct Hotspot {
    std::string Name;
    double Energy;
    double Percent;
};

// For each block, compute percentage of total function energy
for (const auto &BR : FR.Blocks) {
    double Pct = TotalEnergy > 0 ? (BR.Energy / TotalEnergy) * 100.0 : 0.0;
    HotspotList.push_back({BR.Name, BR.Energy, Pct});
}

// Sort descending by energy
std::sort(HotspotList.begin(), HotspotList.end(),
          [](const Hotspot &A, const Hotspot &B) {
              return A.Energy > B.Energy;
          });

// Top 3 are stored in FuncReport.Hotspots
for (size_t i = 0; i < std::min(size_t(3), HotspotList.size()); ++i) {
    FR.Hotspots.push_back({HotspotList[i].Name, HotspotList[i].Energy,
                           HotspotList[i].Percent});
}
```

## Rule-Based Optimization Advisor

The advisor analyzes the instruction mix against fixed thresholds:

| Pattern | Threshold | Suggestion |
|---------|-----------|------------|
| `mul`/`fmul` count ≥ 8% of total | Vectorization / strength reduction |
| `sdiv`/`udiv`/`fdiv` count ≥ 5% | Replace with multiply-by-inverse |
| `load` count ≥ 30% | Improve cache locality |
| `store` count ≥ 20% | Reduce memory writes |
| `load` + `store` count ≥ 40% | Improve data reuse via tiling |
| `call` count ≥ 20% | Consider inlining |

Each advisory includes:
- **Observation** — percentage and cost of the flagged opcode
- **Recommendation** — actionable compiler transformation
- **Potential Benefit** — qualitative description of expected improvement

## Source Heatmap Generation

### LLVM Side (C++)

For each instruction with a valid `DebugLoc`, the pass reads the source line number and accumulates `cost × normalized_frequency`:

```cpp
if (DebugLoc DL = Inst.getDebugLoc()) {
    unsigned Line = DL.getLine();
    if (FR.SourceFile.empty())
        if (MDNode *N = DL.getScope())
            if (DIScope *Scope = dyn_cast_or_null<DIScope>(N))
                FR.SourceFile = Scope->getFilename().str();
    LineEnergy[Line] += Cost * NormalizedFreq;
}
```

### Python Side (visualize.py)

The Python script reads the JSON report and the actual source file, then generates an HTML heatmap with:

- Dark IDE-style code block background
- Line numbers in muted gray
- Background color based on energy intensity:
  - Dark gray — no energy
  - Dark green — low (≤25% of max)
  - Dark yellow — medium (≤50%)
  - Dark orange — high (≤75%)
  - Dark red — very high (>75%)
- `title` attribute for hover tooltips showing line number and energy value
- Legend showing the color scale

## JSON Report Format

```json
{
  "report": {
    "functions": [
      {
        "name": "compute",
        "total_energy": 1150.0,
        "source_file": "test.c",
        "blocks": [
          { "name": "BB_0", "frequency": 1.0, "energy": 22.0 },
          { "name": "BB_1", "frequency": 32.0, "energy": 256.0 }
        ],
        "hotspots": [
          { "name": "BB_2", "energy": 620.0, "percent": 53.91 }
        ],
        "advisories": [
          {
            "observation": "46.43% memory ops (cost: 39.00)",
            "recommendation": "Improve data reuse via tiling or loop interchange",
            "benefit": "Fewer cache misses reduces DRAM access energy"
          }
        ],
        "source_lines": [
          { "line": 7, "energy": 511.0 },
          { "line": 8, "energy": 403.0 }
        ]
      }
    ]
  }
}
```
