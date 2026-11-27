# 07 Pretrain the model

## 1. What and why

Train our transformer from scratch on the corpus with span corruption: random spans of each text are hidden and the model learns to fill them in. This is where the model learns English and general knowledge before it learns to write questions (fine-tuning, a later card).

## 2. Before you start

- Cards 05 and 06 done, and the agent has confirmed which config to use (default `configs/pretrain_small.json`).
- About 10 GB free for checkpoints.
- Plugged in, performance mode, sleep off, cooling pad.

## 3. Commands

Terminal 1, start the run:

```bash
python -m app.lm pretrain --config configs/pretrain_small.json --run pretrain-v1
```

Terminal 2, charts (open the printed address in a browser):

```bash
tensorboard --logdir runs
```

Stop at any time with Ctrl+C once (it saves a checkpoint first). Continue later with:

```bash
python -m app.lm pretrain --resume pretrain-v1
```

A resumed run continues at the same step with the same data order, so stopping does not change the result.

## 4. How long

The time `benchmark` measured for the chosen config (target: at most 5 days). The `left` value in the progress line is the live estimate.

## 5. What you should see

A progress line every 20 steps:

```
step 1,240/33,000 | loss 4.8123 | lr 1.00e-03 | 9,850 tok/s | elapsed 03:12:40 | left 3d 10:05:00 | mem 2.91 GB | GPU 78°C
```

- Loss starts around 10 and should fall below 4 within the first day, then slowly toward 2 to 3.
- Every 2,000 steps: `validation loss ...`; a new best is saved as `best.pt`.
- Every 1,000 steps: samples (also appended to `runs/pretrain-v1/samples.md`) showing the text with blanks, what the model fills in, and the correct answer. Early fills are empty or repeated words; after a day or two they become plausible words.
- A checkpoint every 30 minutes in `runs/pretrain-v1/checkpoints/` (the last 3 are kept).

## 6. How to check it worked

- The run ends with `Training finished.`
- `runs/pretrain-v1/best.pt` exists, and the validation loss in `metrics.csv` went down over the run.
- Check once or twice a day: the loss is falling, the GPU stays under about 87°C, and the samples improve.

## 7. If it fails

- `Loss became nan ...`: the run stopped itself without saving the bad step. Run the command it prints (it resumes with half the learning rate).
- `CUDA out of memory`: send the output; the agent will lower the micro-batch or turn on gradient checkpointing.
- `Only N GB free`: free disk space, then resume.
- Power cut or crash: resume; at most 30 minutes are lost.
- GPU above 90°C for long periods: stop with Ctrl+C, improve cooling, then resume.
- Loss flat above 6 after 5,000 steps: stop and send `metrics.csv` and `samples.md`.

## 8. What to send back

- After the first hour: the last 10 progress lines and the first samples block.
- Once a day: the last progress line and the latest samples block.
- At the end: the last 30 lines of output and `runs/pretrain-v1/metrics.csv`.
