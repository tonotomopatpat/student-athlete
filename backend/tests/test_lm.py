import json
import random
import string

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("sentencepiece")
pytest.importorskip("pyarrow")
pytest.importorskip("tensorboard")

from app.datasets.wikidump import article_markup  # noqa: E402
from app.lm import shards  # noqa: E402
from app.lm.config import ModelConfig, RunConfig, TrainConfig, config_from_dict  # noqa: E402
from app.lm.data import SpanSettings, open_stream, read_meta  # noqa: E402
from app.lm.model import IGNORE_INDEX, Seq2SeqTransformer  # noqa: E402
from app.lm.noise import corrupt, window_lengths  # noqa: E402
from app.lm.tokenizer import Tokenizer, train_tokenizer  # noqa: E402
from app.lm.train import Trainer, latest_checkpoint, learning_rate  # noqa: E402

SENTINELS = list(range(1000, 1100))
WORDS = ["".join(random.Random(i).choices(string.ascii_lowercase, k=3 + i % 6)) for i in range(400)]


def _paragraph(rng: random.Random) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(rng.randint(20, 60))).capitalize() + "."


def _reconstruct(inputs: np.ndarray, targets: np.ndarray) -> list[int]:
    spans, current = {}, None
    for token in targets[:-1]:
        if token in SENTINELS:
            current = SENTINELS.index(token)
            spans[current] = []
        else:
            spans[current].append(int(token))
    out = []
    for token in inputs[:-1]:
        out.extend(spans[SENTINELS.index(token)] if token in SENTINELS else [int(token)])
    return out


def test_window_lengths_match_t5():
    assert window_lengths(512, 0.15, 3.0) == (568, 114)


@pytest.mark.parametrize("seed", range(5))
def test_span_corruption_is_lossless(seed):
    raw, target = window_lengths(64, 0.15, 3.0)
    tokens = np.random.default_rng(seed).integers(3, 900, raw)
    inputs, targets = corrupt(tokens, SENTINELS, 1, 0.15, 3.0, np.random.default_rng(seed))
    assert len(inputs) == 64 and len(targets) <= target
    assert inputs[-1] == targets[-1] == 1
    assert _reconstruct(inputs, targets) == tokens.tolist()


def _tiny_model(vocab: int = 64) -> Seq2SeqTransformer:
    torch.manual_seed(0)
    return Seq2SeqTransformer(ModelConfig(vocab_size=vocab, d_model=32, n_heads=2, d_ff=64,
                                          encoder_layers=1, decoder_layers=1))


def test_model_shapes_and_loss():
    model = _tiny_model()
    inputs = torch.randint(3, 64, (2, 10))
    labels = torch.randint(3, 64, (2, 6))
    labels[1, 4:] = IGNORE_INDEX
    logits, loss = model(inputs, labels)
    assert logits.shape == (2, 6, 64)
    assert torch.isfinite(loss)


def test_decoder_is_causal():
    model = _tiny_model().eval()
    memory, mask = model.encode(torch.randint(3, 64, (1, 8)))
    first = torch.randint(3, 64, (1, 6))
    second = first.clone()
    second[0, 4:] = 5
    with torch.no_grad():
        a, b = model.decode(first, memory, mask), model.decode(second, memory, mask)
    assert torch.allclose(a[:, :4], b[:, :4], atol=1e-5)


def test_encoder_ignores_padding():
    model = _tiny_model().eval()
    inputs = torch.randint(3, 64, (1, 8))
    padded = torch.cat([inputs, torch.zeros(1, 4, dtype=torch.long)], dim=1)
    labels = torch.randint(3, 64, (1, 5))
    with torch.no_grad():
        assert torch.allclose(model(inputs, labels)[0], model(padded, labels)[0], atol=1e-5)


def test_tiny_model_overfits_one_batch():
    model = _tiny_model()
    inputs, labels = torch.randint(3, 64, (4, 12)), torch.randint(3, 64, (4, 6))
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3)
    for _ in range(300):
        loss = model(inputs, labels)[1]
        loss.backward()
        optimizer.step()
        optimizer.zero_grad()
    assert loss.item() < 0.1
    assert torch.equal(model.generate_greedy(inputs[:1], max_new_tokens=6)[0, :6], labels[0])


def test_learning_rate_schedule():
    train = TrainConfig(warmup_steps=10, learning_rate=1e-3, min_lr_ratio=0.1)
    assert learning_rate(0, 100, train) < learning_rate(9, 100, train) <= 1e-3
    assert learning_rate(100, 100, train) == pytest.approx(1e-4)


def test_config_rejects_unknown_keys():
    with pytest.raises(ValueError):
        config_from_dict({"model": {"widht": 3}, "train": {}})


def test_article_markup_stops_at_references():
    text = "First  paragraph here.\n\nSecond one.\n\nReferences\n\nSmith 2001."
    assert article_markup("Moon", text) == "# Moon\n\nFirst paragraph here.\n\nSecond one.\n"


@pytest.fixture(scope="module")
def corpus_dirs(tmp_path_factory):
    root = tmp_path_factory.mktemp("lm")
    clean = root / "clean"
    clean.mkdir()
    rng = random.Random(3)
    for source, documents in (("wikipedia", 60), ("openstax", 20)):
        blocks = ["\n".join(_paragraph(rng) for _ in range(4)) for _ in range(documents)]
        (clean / f"{source}.txt").write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    sample = root / "sample.txt"
    shards.write_tokenizer_sample(clean, sample, max_lines=10_000)
    train_tokenizer(sample, root / "tokenizer", vocab_size=800, max_sentences=10_000, hard_vocab_limit=False)
    return root, clean, Tokenizer(root / "tokenizer")


def test_tokenizer_round_trip(corpus_dirs):
    _, _, tokenizer = corpus_dirs
    text = f"{WORDS[0]} {WORDS[1]} and {WORDS[2]}."
    assert tokenizer.decode(tokenizer.encode(text)) == text
    assert tokenizer.decode([tokenizer.highlight_id]) == "<hl>"
    assert len(tokenizer.sentinel_ids) == 100


def test_shards_round_trip(corpus_dirs, tmp_path, monkeypatch):
    _, clean, tokenizer = corpus_dirs
    monkeypatch.setattr(shards, "VAL_PER_MILLE", 300)
    meta = shards.build_shards(clean, tokenizer, tmp_path, shard_tokens=5_000, progress=lambda *_: None)
    assert meta == read_meta(tmp_path)
    assert meta["tokenizer_sha256"] == tokenizer.sha256() and meta["val_tokens"] > 0
    assert meta["sources"]["openstax"]["train_tokens"] > 0
    tokens = np.fromfile(tmp_path / meta["train_files"][0], dtype=np.uint16)
    first_document = tokens[:int(np.argmax(tokens == tokenizer.eos_id))]
    assert tokenizer.decode(first_document.tolist()).split()[0][0].isupper()
    with pytest.raises(FileExistsError):
        shards.build_shards(clean, tokenizer, tmp_path, progress=lambda *_: None)


def _trainer(run_dir, shards_dir, tokenizer, total_tokens):
    config = RunConfig(
        ModelConfig(vocab_size=tokenizer.vocab_size, d_model=32, n_heads=2, d_ff=64, encoder_layers=1,
                    decoder_layers=1),
        TrainConfig(input_length=32, micro_batch_size=2, grad_accum_steps=2, warmup_steps=2, total_tokens=total_tokens,
                    precision="fp32", log_every=1, eval_every=3, eval_batches=2, sample_every=1000),
        shards=str(shards_dir))
    settings = SpanSettings(32, 0.15, 3.0, tuple(tokenizer.sentinel_ids), tokenizer.eos_id)
    raw = settings.lengths[0]
    train = open_stream(shards_dir, "train", settings, 2, 1234, tokenizer.pad_id, max_windows=total_tokens // raw)
    val = open_stream(shards_dir, "val", settings, 2, 1235, tokenizer.pad_id)
    return Trainer(run_dir, config, train, val, tokenizer, device=torch.device("cpu"), out=lambda *_: None)


def test_resume_matches_uninterrupted_run(corpus_dirs, tmp_path, monkeypatch):
    _, clean, tokenizer = corpus_dirs
    monkeypatch.setattr(shards, "VAL_PER_MILLE", 300)
    shards_dir = tmp_path / "shards"
    shards.build_shards(clean, tokenizer, shards_dir, progress=lambda *_: None)
    budget = 8 * 4 * window_lengths(32, 0.15, 3.0)[0]

    straight = _trainer(tmp_path / "straight", shards_dir, tokenizer, budget)
    straight.start_new()
    straight.run(max_steps=6)

    first = _trainer(tmp_path / "split", shards_dir, tokenizer, budget)
    first.start_new()
    first.run(max_steps=3)
    with pytest.raises(FileExistsError):
        first.start_new()
    second = _trainer(tmp_path / "split", shards_dir, tokenizer, budget)
    second.resume()
    assert second.state.step == 3
    second.run(max_steps=6)

    assert second.state.windows == straight.state.windows
    for name, value in straight.model.state_dict().items():
        assert torch.equal(value, second.model.state_dict()[name]), name
    assert (tmp_path / "split" / "best.pt").is_file()
    assert json.loads((tmp_path / "split" / "state.json").read_text())["step"] == 6
    assert latest_checkpoint(tmp_path / "split").name == "step-00000006.pt"
