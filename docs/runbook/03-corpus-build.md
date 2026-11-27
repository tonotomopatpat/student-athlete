# 03 Clean and filter the corpus

## 1. What and why

Turn all downloaded text into clean plain text: drop exact duplicate paragraphs, very short documents, non-English text, and index or answer-key pages. It also removes any text that overlaps our gold test lessons, so the model never sees the test material during training (a requirement for a fair evaluation).

## 2. Before you start

- Card 02 done.
- If gold lessons already exist on the Mac, copy `backend/data/gold/` to the same place on the ASUS first (it is not in git). The overlap filter reads them. If there are none yet, continue: when the test lessons are collected, a contamination check compares them against this corpus, and any overlapping test lesson is replaced. Pretraining is not repeated.
- About 10 GB free.

## 3. Commands

```bash
python -m app.lm corpus-build
python -m app.lm corpus-report
```

## 4. How long

1 to 2 hours (one CPU core, mostly Wikipedia).

## 5. What you should see

A progress line every 100,000 documents, then a report per source: documents kept, words kept, and how many were dropped for each reason.

## 6. How to check it worked

- `data/corpus/clean/` has `openstax.txt`, `wiki-en.txt`, `wiki-simple.txt` and `report.json`.
- `corpus-report` shows roughly 700 to 900 million words in total.
- `Gold lessons used for the overlap filter` equals the number of gold lessons you copied (0 is fine if none exist yet).

## 7. If it fails

- Out of memory: close other programs and run again (it starts over; about 3 GB of RAM is used for duplicate detection).

## 8. What to send back

The full output of `corpus-report`.
