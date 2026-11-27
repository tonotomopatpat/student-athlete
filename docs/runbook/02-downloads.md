# 02 Download the pretraining text

## 1. What and why

Download the open text the model learns English from: OpenStax textbooks (CC BY), the Universal Dependencies treebanks (used by the tagger), and Wikipedia (CC BY-SA, the `wikimedia/wikipedia` 2023-11-01 dump). Each source and its license is recorded in `data/corpus/manifest.json` for the thesis.

## 2. Before you start

- Card 01 passed.
- About 15 GB free (Wikipedia Parquet files are deleted after conversion).
- A stable connection.

## 3. Commands

From `backend/` with `.venv-train` active:

```bash
python -m app.cli fetch-corpus --openstax --treebanks
python -m app.lm wiki-download --lang en --shards 8
python -m app.lm wiki-download --lang simple --shards all
```

`--shards 8` is the first 8 of 41 English Wikipedia files, about 1 billion tokens, which is enough for our token budget. Do not change it without asking.

## 4. How long

1 to 3 hours depending on the connection (Wikipedia English is about 2.3 GB to download).

## 5. What you should see

One line per downloaded file and per converted shard, then:

```
Done: 1,6xx,xxx articles, 9xx,xxx,xxx words (20231101.en shards 1-8 of 41). Recorded in manifest.json.
```

Files appear in `data/corpus/openstax/`, `data/corpus/treebanks/` and `data/corpus/wikidump/` (`en-00000.jsonl` to `en-00007.jsonl`, `simple-00000.jsonl`).

## 6. How to check it worked

```bash
ls data/corpus/wikidump/*.jsonl | wc -l
```

prints `9`, and `data/corpus/manifest.json` lists OpenStax and both Wikipedia downloads.

## 7. If it fails

- Network error, `incomplete download`, or Ctrl+C: run the same command again. Finished shards are skipped; the interrupted one starts over.
- Hugging Face rate limit (HTTP 429): wait 10 minutes and run again.

## 8. What to send back

The last 5 lines of each command, and the output of `ls -la data/corpus/wikidump/`.
