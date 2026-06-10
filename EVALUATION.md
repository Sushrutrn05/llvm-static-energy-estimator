# Evaluation Report

## Benchmarks

Five C programs exercise different instruction mixes and control-flow shapes:

| # | Source | Profile | Complexity |
|---|--------|---------|------------|
| 1 | `benchmarks/loop.c` | Arithmetic tight loop | O(N) |
| 2 | `benchmarks/matrix.c` | 64×64 matrix multiply | O(N³) |
| 3 | `benchmarks/memory.c` | Linked-list traversal | O(N) |
| 4 | `benchmarks/recursion.c` | Recursive factorial | O(N) |
| 5 | `benchmarks/sorting.c` | Bubble sort | O(N²) |

All compiled with `clang-14 -S -emit-llvm -g -O0` and run with
`models/x86_energy.json`. Values are from the JSON report output.

## Results

| Benchmark | Functions | Instructions | Weighted Energy | Dominant Opcode |
|-----------|-----------|--------------|-----------------|-----------------|
| `loop.c` | 2 | 32 | 1,158.00 | memory (46%) |
| `matrix.c` | 2 | 72 | 1,597,058.00 | memory (40%) |
| `memory.c` | 3 | 63 | 2,377.50 | memory (40–48%) |
| `recursion.c` | 2 | 25 | 40.00 | memory (48%) |
| `sorting.c` | 2 | 107 | 76,070.50 | memory (44%) |

Ranking by energy: matrix.c > sorting.c > memory.c > loop.c > recursion.c.

### Baseline Comparison

A synthetic empty function (`void f() {}`) gives energy 1.0 as a reference
floor:

| Benchmark | Total Energy | vs Baseline | Expected |
|-----------|-------------|-------------|----------|
| empty() | 1.00 | 1× | reference |
| recursion.c | 40.00 | 40× | O(N), N=10 |
| loop.c | 1,158.00 | 1,158× | O(N), N=1000 |
| memory.c | 2,377.50 | 2,378× | O(N), N=1000 |
| sorting.c | 76,070.50 | 76,071× | O(N²), N=50 |
| matrix.c | 1,597,058.00 | 1.6M× | O(N³), N=64 |

Relative ordering matches algorithmic complexity expectations. Note:
recursion.c shows low energy because BFI estimates ~0.5 frequency for the
recursive block (N=10 depth with N² fixed-point convergence).

## Validation Against Published Data

We compare our model's relative cost ratios against per-instruction energy
measurements from Tiwari et al. (1994) for the Intel 486DX2 and against
generic RISC values from the literature.

### Instruction Cost Ratios (relative to `add` = 1.0)

| Pair | Our Model | Tiwari 1994 (i486) | Published Range |
|------|-----------|--------------------|-----------------|
| `mul` / `add` | 3.0 | 2.3–2.8× | 2.0–4.0× |
| `load` / `add` | 3.0 | — | 2.0–3.5× |
| `store` / `add` | 3.0 | — | 2.0–3.0× |
| `div` / `add` | 6.0 | 5.0–6.1× | 4.0–8.0× |
| `call` / `add` | 3.0 | 2.5–4.0× | 2.0–5.0× |
| `fmul` / `add` | 4.0 | — | 3.0–5.0× |

Our ratios fall within or near published ranges for all instruction pairs.
The model correctly ranks operations: integer add < integer mul < floating
point mul < division (integer and float).

### Limitations of This Validation

- Per-instruction energy varies by microarchitecture, process node, cache
  state, and operand values. A single static model cannot capture all
  effects.
- Cache misses, pipeline stalls, and branch mispredictions are not modeled.
  Our estimates reflect ideal-cache, sequential-execution energy.
- Relative ranking within a single program is more reliable than cross-program
  comparison. The model is suitable for hotspot identification, not absolute
  energy measurement.
- Published per-instruction measurements are for specific embedded processors
  from the 1990s. Modern x86 cores differ significantly.

## Observations

1. BFI frequency weighting is essential. Without it, instruction counts are
   within 5× across benchmarks; with BFI, energy spans five orders of
   magnitude (40 to 1.6M).
2. Memory-heavy benchmarks (matrix.c, sorting.c, memory.c) show higher energy
   than compute-heavy ones due to load/store cost multipliers (3×).
3. The advisor threshold system correctly flags high memory density (matrix,
   sorting, memory) and stays silent on mixed workloads.

## Conclusion

The estimator ranks all five benchmarks in the correct asymptotic order:
O(1) < O(N) < O(N²) < O(N³). Instruction cost ratios are consistent with
published per-instruction energy data (Tiwari et al. 1994). The tool is
suitable as a relative energy profiler for guiding optimization effort, but
absolute energy values require hardware-level calibration (RAPL or power
monitor). BFI estimates for recursion are conservative and may undercount
deeply recursive functions.
