"""Training commands, run by the user: python -m app.lm <command>. See docs/runbook/ for when to run each."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from app.core.config import BACKEND_DIR
from app.datasets import corpus, pretext, wikidump
from app.lm import benchmark, doctor, shards
from app.lm.config import RunConfig, config_from_dict, load_config, resolve
from app.lm.data import SpanSettings, corrupt_window, open_stream, read_meta
from app.lm.tokenizer import Tokenizer, train_tokenizer
from app.lm.train import Trainer, TrainingDiverged, pick_device

RUNS_DIR = BACKEND_DIR / "runs"
RESULTS_DIR = BACKEND_DIR / "evaluation" / "results"
SAMPLE_TOKENS = 64


def cmd_doctor(_args: argparse.Namespace) -> None:
    sys.exit(doctor.print_report())


def cmd_wiki_download(args: argparse.Namespace) -> None:
    limit = None if args.shards == "all" else int(args.shards)
    entry = wikidump.fetch_dump(args.lang, limit, keep_parquet=args.keep_parquet)
    corpus.update_manifest([entry])
    print(f"Done: {entry['articles']:,} articles, {entry['words']:,} words ({entry['selection']}). "
          f"Recorded in {corpus.CORPUS_MANIFEST.name}.")


def cmd_corpus_build(args: argparse.Namespace) -> None:
    report = pretext.build_clean_corpus(resolve(args.out))
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "corpus_build.json").write_text(json.dumps(report, indent=2))
    _print_build_report(report)


def _print_build_report(report: dict) -> None:
    print(f"Gold lessons used for the overlap filter: {report['gold_lessons']}")
    for source, counts in report["sources"].items():
        dropped = {key: value for key, value in counts.items() if key.startswith("dropped") or "duplicate" in key}
        print(f"{source:<12} kept {counts.get('documents_kept', 0):,} of {counts.get('documents_in', 0):,} documents, "
              f"{counts.get('words_kept', 0):,} words | " + ", ".join(f"{k} {v:,}" for k, v in dropped.items()))
    print(f"Total words kept: {report['words_kept']:,}")


def cmd_corpus_report(args: argparse.Namespace) -> None:
    clean_report = resolve(args.clean) / pretext.REPORT_FILE
    if clean_report.is_file():
        _print_build_report(json.loads(clean_report.read_text()))
    else:
        print("No clean corpus yet (run corpus-build).")
    try:
        meta = read_meta(resolve(args.shards))
    except FileNotFoundError:
        print("No shards yet (run corpus-shards).")
        return
    print(f"\nShards: {meta['train_tokens']:,} training tokens, {meta['val_tokens']:,} validation tokens, "
          f"{len(meta['train_files'])} training files")
    for source, counts in meta["sources"].items():
        print(f"{source:<12} {counts.get('train_tokens', 0):,} training tokens "
              f"(repeat x{meta['repeats'].get(source, 1)}), {counts.get('val_tokens', 0):,} validation tokens")


def cmd_tokenizer_train(args: argparse.Namespace) -> None:
    out_dir = resolve(args.out)
    sample = out_dir / "train_sample.txt"
    written = shards.write_tokenizer_sample(resolve(args.clean), sample, args.sentences)
    print("Sample paragraphs per source: " + ", ".join(f"{source} {count:,}" for source, count in written.items()))
    meta = train_tokenizer(sample, out_dir, vocab_size=args.vocab, max_sentences=args.sentences)
    sample.unlink()
    tokenizer = Tokenizer(out_dir)
    example = "Photosynthesis is the process by which plants convert light energy into chemical energy."
    pieces = tokenizer.sp.encode(example, out_type=str)
    print(f"Tokenizer saved to {out_dir}: {meta['vocab_size']:,} pieces, sha256 {meta['sha256'][:12]}")
    print(f"Example ({len(pieces)} pieces): {' '.join(pieces)}")


def cmd_corpus_shards(args: argparse.Namespace) -> None:
    tokenizer = Tokenizer(resolve(args.tokenizer))
    meta = shards.build_shards(resolve(args.clean), tokenizer, resolve(args.out),
                               repeats={"openstax": args.openstax_repeat})
    print(f"Done: {meta['train_tokens']:,} training tokens and {meta['val_tokens']:,} validation tokens in "
          f"{resolve(args.out)}")


def cmd_benchmark(args: argparse.Namespace) -> None:
    configs = {Path(path).stem: load_config(path) for path in args.configs}
    benchmark.run(configs, pick_device(args.device), RESULTS_DIR / "benchmark.json", steps=args.steps)


def _settings(config: RunConfig, tokenizer: Tokenizer) -> SpanSettings:
    return SpanSettings(config.train.input_length, config.train.noise_density, config.train.mean_span_length,
                        tuple(tokenizer.sentinel_ids), tokenizer.eos_id)


def _run_dir(name: str) -> Path:
    path = Path(name)
    return path if path.is_absolute() or path.parent != Path(".") else RUNS_DIR / name


def cmd_pretrain(args: argparse.Namespace) -> None:
    if bool(args.resume) == bool(args.run):
        sys.exit("Give either --run NAME (new run) or --resume NAME (continue a run).")
    run_dir = _run_dir(args.resume or args.run)
    if args.resume and not (run_dir / "config.json").is_file():
        sys.exit(f"No run at {run_dir}. Check the name with: ls {RUNS_DIR}")
    config = (config_from_dict(json.loads((run_dir / "config.json").read_text())) if args.resume
              else load_config(args.config))
    tokenizer = Tokenizer(config.tokenizer_dir)
    if tokenizer.vocab_size != config.model.vocab_size:
        sys.exit(f"Tokenizer has {tokenizer.vocab_size} pieces but the config says {config.model.vocab_size}.")
    meta = read_meta(config.shards_dir)
    if meta["tokenizer_sha256"] != tokenizer.sha256():
        sys.exit("The shards were made with a different tokenizer. Rebuild them with corpus-shards.")
    settings = _settings(config, tokenizer)
    raw_length = settings.lengths[0]
    train = config.train
    train_stream = open_stream(config.shards_dir, "train", settings, train.micro_batch_size, train.seed,
                               tokenizer.pad_id, max_windows=train.total_tokens // raw_length)
    val_stream = open_stream(config.shards_dir, "val", settings, train.micro_batch_size, train.seed + 1,
                             tokenizer.pad_id) if meta["val_files"] else None
    samples = []
    if val_stream is not None:
        sample_settings = SpanSettings(SAMPLE_TOKENS, train.noise_density, train.mean_span_length,
                                       settings.sentinel_ids, settings.eos_id)
        for index in range(min(3, len(val_stream))):
            window = val_stream.windows[int(val_stream.order[index])][:sample_settings.lengths[0]]
            samples.append(corrupt_window(np.asarray(window), sample_settings, train.seed, index))
    trainer = Trainer(run_dir, config, train_stream, val_stream, tokenizer, samples, pick_device(args.device))
    if args.resume:
        trainer.resume(lr_scale=args.lr_scale)
    else:
        trainer.start_new()
    print(f"Run folder: {run_dir}\nWatch the charts: tensorboard --logdir {RUNS_DIR}")
    try:
        trainer.run(max_steps=args.max_steps)
    except TrainingDiverged as error:
        sys.exit(str(error))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.lm", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="check GPU, memory, disk and packages").set_defaults(func=cmd_doctor)

    wiki = sub.add_parser("wiki-download", help="download Wikipedia text (wikimedia/wikipedia dump)")
    wiki.add_argument("--lang", choices=sorted(wikidump.CONFIGS), default="en")
    wiki.add_argument("--shards", default="8", help="number of Parquet shards, or 'all'")
    wiki.add_argument("--keep-parquet", action="store_true", help="keep the downloaded Parquet files")
    wiki.set_defaults(func=cmd_wiki_download)

    build = sub.add_parser("corpus-build", help="clean, de-duplicate and gold-filter all corpus text")
    build.add_argument("--out", default="data/corpus/clean")
    build.set_defaults(func=cmd_corpus_build)

    report = sub.add_parser("corpus-report", help="summary of the clean corpus and the shards")
    report.add_argument("--clean", default="data/corpus/clean")
    report.add_argument("--shards", default="data/corpus/shards")
    report.set_defaults(func=cmd_corpus_report)

    tokenizer = sub.add_parser("tokenizer-train", help="train our SentencePiece tokenizer")
    tokenizer.add_argument("--clean", default="data/corpus/clean")
    tokenizer.add_argument("--out", default="models/tokenizer/v1")
    tokenizer.add_argument("--sentences", type=int, default=2_000_000)
    tokenizer.add_argument("--vocab", type=int, default=32_000)
    tokenizer.set_defaults(func=cmd_tokenizer_train)

    shard = sub.add_parser("corpus-shards", help="tokenize the clean corpus into training shards")
    shard.add_argument("--clean", default="data/corpus/clean")
    shard.add_argument("--tokenizer", default="models/tokenizer/v1")
    shard.add_argument("--out", default="data/corpus/shards")
    shard.add_argument("--openstax-repeat", type=int, default=3)
    shard.set_defaults(func=cmd_corpus_shards)

    bench = sub.add_parser("benchmark", help="measure speed and memory per model size (rule G1)")
    bench.add_argument("--configs", nargs="+", default=["configs/pretrain_small.json", "configs/pretrain_tiny.json"])
    bench.add_argument("--steps", type=int, default=8)
    bench.add_argument("--device", default="auto")
    bench.set_defaults(func=cmd_benchmark)

    pre = sub.add_parser("pretrain", help="pretrain the model (new run or resume)")
    pre.add_argument("--config", default="configs/pretrain_small.json")
    pre.add_argument("--run", help="name of a new run folder under runs/")
    pre.add_argument("--resume", help="name of the run to continue")
    pre.add_argument("--lr-scale", type=float, help="multiply the learning rate, e.g. 0.5 after a divergence")
    pre.add_argument("--max-steps", type=int, help="stop (with a checkpoint) after this many steps")
    pre.add_argument("--device", default="auto")
    pre.set_defaults(func=cmd_pretrain)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
