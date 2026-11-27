# 06 Measure speed per model size (rule G1)

## 1. What and why

Measure how fast each model size trains on the RTX 3050 and whether it fits in GPU memory. Rule G1 picks the largest size that finishes the token budget (1.2 billion tokens) within 5 days. This decides which config card 07 uses.

## 2. Before you start

- Card 01 passed. (The corpus is not needed; the benchmark uses random data.)
- Plugged in, performance mode, nothing else using the GPU.

## 3. Commands

```bash
python -m app.lm benchmark
```

## 4. How long

About 10 minutes.

## 5. What you should see

For each size (`pretrain_small`, about 60M parameters, and `pretrain_tiny`, about 30M), one line with tokens per second, peak memory and hours for the budget. If a size does not fit, it retries with a smaller micro-batch and gradient checkpointing. Then:

```
Rule G1: Use pretrain_small: about 3.8 days for 1.2B tokens with micro-batch 8.
Saved to .../evaluation/results/benchmark.json
```

## 6. How to check it worked

`evaluation/results/benchmark.json` exists and has a `recommendation`.

## 7. If it fails

- `No size fits in memory`: send the output.
- Very low speed (under 5,000 tokens per second for tiny): check that `doctor` says cuda and the laptop is in performance mode, then run again.

## 8. What to send back

The `Rule G1` line and the two measurement lines. The agent then sets the micro-batch and gradient checkpointing in the chosen config, and card 07 tells you which config to use.
