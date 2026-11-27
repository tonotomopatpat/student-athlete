# 04 Train the tokenizer

## 1. What and why

Train our own SentencePiece tokenizer (32,000 pieces) on a sample of the clean corpus. It splits text into the pieces the model reads and writes. It is part of the model, so it is trained once and never changed afterwards.

## 2. Before you start

- Card 03 done.
- About 8 GB of free RAM (close the browser).

## 3. Commands

```bash
python -m app.lm tokenizer-train
```

Defaults: 2,000,000 sample paragraphs, 32,000 pieces, saved to `models/tokenizer/v1/`.

## 4. How long

30 to 90 minutes.

## 5. What you should see

The sample size per source, SentencePiece training logs, then:

```
Tokenizer saved to .../models/tokenizer/v1: 32,000 pieces, sha256 ...
Example (14 pieces): ▁Photo synthesis ▁is ▁the ▁process ...
```

## 6. How to check it worked

`models/tokenizer/v1/` has `spm.model` and `tokenizer.json`, and the example sentence splits into about 12 to 20 pieces of mostly whole words.

## 7. If it fails

- Killed or out of memory: run again with `--sentences 1000000`.
- `Vocabulary size is too high`: the corpus is too small; send the output of `corpus-report`.

## 8. What to send back

The last 5 lines of output.
