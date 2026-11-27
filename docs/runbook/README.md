# Runbook

Every important step (downloads, corpus builds, training, evaluation runs, freezing, migrations, deployment) is started by you, not the agent. Each step has a run card here, in the order to run them. After each step, send back what the card's last section asks for; the agent continues only after reviewing it.

All training commands are `python -m app.lm <command>`, run from `backend/` with the training environment active (`source .venv-train/bin/activate`). `python -m app.lm --help` lists them.

| Card | Step | Machine | Time |
| --- | --- | --- | --- |
| [01](01-asus-setup.md) | Set up the ASUS and run `doctor` | ASUS | 1 to 2 hours |
| [02](02-downloads.md) | Download OpenStax, treebanks and Wikipedia | ASUS | 1 to 3 hours |
| [03](03-corpus-build.md) | Clean and filter the corpus | ASUS | 1 to 2 hours |
| [04](04-tokenizer.md) | Train the tokenizer | ASUS | 30 to 90 minutes |
| [05](05-corpus-shards.md) | Tokenize the corpus into shards | ASUS | 1 to 2 hours |
| [06](06-benchmark.md) | Measure speed per model size (rule G1) | ASUS | about 10 minutes |
| [07](07-pretrain.md) | Pretrain the model | ASUS | days |

Later cards (fine-tuning, evaluation, freezing) are added when their code is ready.

## Run card format

1. What and why
2. Before you start
3. Commands
4. How long
5. What you should see
6. How to check it worked
7. If it fails
8. What to send back

## Token-saving scripts

Scripts in `backend/scripts/tools/` do work that would cost the agent many tokens (reading big files, checking thousands of records). They write full results to `backend/scripts/tools/out/` (git-ignored) and print a summary of at most 30 lines, which is what you send back. Reusable ones are listed here.

None yet.
