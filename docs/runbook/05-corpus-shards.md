# 05 Tokenize the corpus into shards

## 1. What and why

Convert the clean text into token files the trainer reads quickly from disk. OpenStax is repeated 3 times because it is closest to the lessons students upload. About 0.5% of documents go to a separate validation set used to measure progress during training.

## 2. Before you start

- Card 04 done.
- About 5 GB free.

## 3. Commands

```bash
python -m app.lm corpus-shards
python -m app.lm corpus-report
```

## 4. How long

1 to 2 hours (uses all CPU cores).

## 5. What you should see

Progress per source, then `Done: N training tokens and M validation tokens`. Files `train-00000.bin`, ..., `val-00000.bin` and `meta.json` appear in `data/corpus/shards/`.

## 6. How to check it worked

`corpus-report` shows about 1.1 to 1.4 billion training tokens and a few million validation tokens.

## 7. If it fails

- `already has shards`: a previous run exists. If it was interrupted, delete `data/corpus/shards/` and run again.
- Fewer than 1 billion training tokens: send the report; the agent will adjust the token budget.

## 8. What to send back

The full output of `corpus-report`.
