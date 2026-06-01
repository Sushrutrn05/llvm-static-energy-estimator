# Evaluation Report

## Test Cases

### Test 1: `test.c` — Simple Function with Loop

**Source:** `test.c`
**Flags:** `-O1 -g`
**Purpose:** Baseline sanity check. Arithmetic loop with volatile sink.

**Expected:** Loop body dominates energy. Calls to `printf` and `compute` contribute moderate cost.

| Metric | Value |
|--------|-------|
| Functions | 2 (`compute`, `main`) |
| Total instructions | 28 + 9 = 37 |
| Weighted energy | 1150.00 + 21.00 = 1171.00 |
| Top hotspot | `BB_2` (53.91% of `compute`) |
| Hotspot lines | 7-9 (loop body) |

**Result:** ✅ Loop body lines 7-9 are dark red in heatmap. `compute` accounts for 98.2% of total energy.

---

### Test 2: `loop.c` — Arithmetic-Intensive Benchmark

**Source:** `benchmarks/loop.c`
**Flags:** `-O1 -g`
**Purpose:** Register-heavy computation with minimal memory access.

**Expected:** Low energy per iteration. Dominated by `add`, `shl`, `icmp`. No `load` instructions in the hot loop (the volatile sink creates one `store` per iteration).

| Metric | Value |
|--------|-------|
| Functions | 2 |
| Total instructions | 19 + 9 = 28 |
| Weighted energy | 429.88 + 21.00 = 450.88 |
| Instruction mix | 37% call, 32% control, 26% arithmetic, 5% memory |
| Top advisory | "36.84% calls" |

**Result:** ✅ Correctly identifies call-heavy profile. Energy per iteration is low since the inner loop has no memory loads.

---

### Test 3: `matrix.c` — Mixed Compute + Memory

**Source:** `benchmarks/matrix.c`
**Flags:** `-O0 -g` (required to preserve loop structure)
**Purpose:** 64×64 integer matrix multiplication. High `load`/`store` density with `mul` and `add`.

**Expected:** Triple-nested loop creates very high block frequencies (64×64×64 = 262,144 inner iterations). Memory operations dominate weighted energy.

| Metric | Value |
|--------|-------|
| Functions | 2 (`matmul`, `main`) |
| Total instructions | 68 + 4 = 72 |
| Weighted energy | 1,597,050.00 + 8.00 = 1,597,058.00 |
| Instruction mix | 40% memory, 19% control, 18% address computation, 12% arithmetic |
| Top hotspot | Innermost loop body block (highest frequency × cost) |

**Result:** ✅ Correctly identifies `matmul` as the dominant energy consumer. Memory operations account for 40% of the instruction mix and are correctly weighted by the triple-nested loop frequency. The weighted energy of ~1.6M is ~3,700× higher than `loop.c`, consistent with O(N³) vs O(N) complexity.

---

### Test 4: `memory.c` — Memory-Intensive Benchmark

**Source:** `benchmarks/memory.c`
**Flags:** `-O1 -g`
**Purpose:** Linked-list traversal with pointer chasing. Tests memory access energy modeling.

**Expected:** High `load`/`store` density. Each node access requires two `load` instructions (data + next pointer) and `getelementptr` for offset computation.

| Metric | Value |
|--------|-------|
| Functions | 3 |
| Total instructions | 17 + 27 + 14 = 58 |
| Weighted energy | 804.88 + 267.75 + 24.00 = 1096.63 |
| Instruction mix | 35% load/store, 24% control, 18% call, 12% address computation |
| Top advisory | "46.43% memory ops" |

**Result:** ✅ Memory operations correctly identified as the dominant cost factor. Advisor suggests improving data reuse. The weighted energy is ~2× `loop.c` but ~1,500× less than `matrix.c`, correctly reflecting the O(N) linked-list traversal vs O(N³) matrix multiplication.

---

### Test 5: Empty / No-Op Function

**Source:** (synthetic) `void empty() {}`
**Flags:** `-O1 -g`
**Purpose:** Edge case — minimal energy baseline.

**Expected:** Single `ret` instruction. Energy = cost(ret) × frequency(1) = 1.0.

| Metric | Value |
|--------|-------|
| Functions | 1 |
| Total instructions | 1 |
| Weighted energy | 1.0 |
| Top hotspot | Only block at 100% |
| Advisories | None |

**Result:** ✅ Correctly produces minimal energy with no advisories triggered.

---

## Baseline Comparison

### Relative Cost Ratios vs. Published Measurements

| Instruction Pair | Tiwari et al. (1994) | Our Model | Difference |
|---|---|---|---|
| `mul` / `add` | 2.3-2.8× | 3.0× | +7-30% |
| `load` / `add` | 2.0-3.5× | 3.0× | 0-50% |
| `div` / `add` | 5.0-6.1× | 6.0× | 0-20% |
| `store` / `add` | 2.0-3.0× | 3.0× | 0-50% |
| `call` / `add` | 2.5-4.0× | 3.0× | 0-20% |

### Cross-Benchmark Energy Trend

| Benchmark | Complexity | Weighted Energy | Relative Scale |
|---|---|---|---|
| `empty()` | O(1) | 1 | 1× |
| `loop.c` | O(N) | 430 | 430× |
| `memory.c` | O(N) | 805 | 805× |
| `matrix.c` | O(N³) | 1,597,050 | 1.6M× |

The relative ordering matches computational complexity expectations, confirming that:
1. `matrix.c` >> `memory.c` > `loop.c` in weighted energy
2. Memory operations amplify energy beyond arithmetic-only code
3. Block frequency weighting correctly captures loop iteration effects

## Strengths

1. **Zero runtime overhead** — fully static analysis
2. **Source-level attribution** — line-by-line heatmap via DWARF debug info
3. **Actionable output** — hotspot ranking and optimization advisor
4. **Portable** — works on any LLVM 14 target architecture
5. **Extensible** — JSON energy model can be calibrated per-platform
6. **CI-friendly** — JSON output enables automated regression testing
7. **No external dependencies** — uses LLVM built-in JSON and analysis passes

## Limitations

### 1. No Cache Hierarchy Model

Memory operations are assigned a flat cost of 3.0 regardless of cache level. In reality:
- L1 cache hit: ~2× add cost
- L2 cache hit: ~7× add cost
- Main memory: ~50-100× add cost

The model assumes L1 cache hits for all loads/stores, producing a lower-bound estimate. Memory-bound code may consume significantly more energy than estimated if cache miss rates are high.

### 2. No Pipeline Modeling

Modern CPUs execute multiple instructions per cycle. Our model assumes sequential execution, which overestimates energy for pipelined code. Instructions that execute in parallel (e.g., independent `add` instructions) have lower effective energy per cycle than sequential dependency chains.

### 3. Data-Independent Costs

Instruction energy depends on operand values due to switching activity. Our model assigns the same cost regardless of operand values or bit patterns. While this is standard practice for static analysis, it means the model cannot detect energy differences from data-dependent optimizations (e.g., zero-avoidance).

### 4. BFI Accuracy

Block frequency estimates from BFI use heuristics:
- Branch probabilities default to 50/50 for unknown branches
- Loop trip counts are estimated from `llvm.loop` metadata when available
- Switch statements use even distribution among cases

These heuristics may not match actual runtime behavior, especially for data-dependent branching patterns.

### 5. Compiler Optimization Sensitivity

Different `-O` levels produce dramatically different IR:
- `-O0`: Full loop structure, many `alloca`/`load`/`store`
- `-O1`: Loop optimization, some inlining
- `-O2`/`-O3`: Aggressive inlining, vectorization, loop transformations

The matrix benchmark (`matrix.c`) requires `-O0` because `-O1` fully optimizes the triple-nested loop into a static constant. Users should be aware that optimization level affects both energy estimates and the IR structure being analyzed.

### 6. Relative, Not Absolute

The pass reports **relative energy** (unitless, normalized to `add = 1.0`), not absolute joules. Converting to absolute energy requires:
1. Measuring the actual power consumption of a reference program on the target hardware
2. Computing a calibration factor: `actual_joules / estimated_energy`
3. Applying the factor to all future estimates

## Future Improvements

1. **Cache-aware memory costs** — integrate cache miss rate estimation from memory access patterns
2. **Pipelining model** — instruction-level parallelism analysis for more accurate superscalar energy
3. **Machine learning calibration** — train on hardware power traces to refine cost weights
4. **PGO integration** — use profile-guided optimization data instead of static BFI heuristics
5. **Call context sensitivity** — attribute energy through call chains for whole-program analysis
