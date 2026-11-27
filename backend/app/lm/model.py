"""Encoder-decoder transformer (Vaswani et al. 2017) in the T5 style (Raffel et al. 2020), written from scratch.

Pre-normalization with RMSNorm, rotary position embeddings in self-attention (Su et al. 2021), GELU feed-forward
layers and input and output embeddings that share weights. All weights start random.
"""

import math

import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.checkpoint import checkpoint

from app.lm.config import ModelConfig

IGNORE_INDEX = -100


class RMSNorm(nn.Module):
    def __init__(self, dim: int, eps: float = 1e-6) -> None:
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        normed = x.float() * torch.rsqrt(x.float().pow(2).mean(-1, keepdim=True) + self.eps)
        return normed.type_as(x) * self.weight


class Rotary(nn.Module):
    def __init__(self, head_dim: int, max_positions: int, base: float = 10_000.0) -> None:
        super().__init__()
        inv_freq = 1.0 / (base ** (torch.arange(0, head_dim, 2).float() / head_dim))
        angles = torch.outer(torch.arange(max_positions).float(), inv_freq)
        self.register_buffer("cos", angles.cos(), persistent=False)
        self.register_buffer("sin", angles.sin(), persistent=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, heads, length, head_dim)."""
        length = x.shape[-2]
        if length > self.cos.shape[0]:
            raise ValueError(f"sequence of {length} tokens is longer than max_positions {self.cos.shape[0]}")
        cos, sin = self.cos[:length].to(x.dtype), self.sin[:length].to(x.dtype)
        first, second = x[..., ::2], x[..., 1::2]
        rotated = torch.stack((first * cos - second * sin, first * sin + second * cos), dim=-1)
        return rotated.flatten(-2)


class Attention(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.heads = config.n_heads
        self.head_dim = config.d_model // config.n_heads
        self.dropout = config.dropout
        self.query = nn.Linear(config.d_model, config.d_model, bias=False)
        self.key = nn.Linear(config.d_model, config.d_model, bias=False)
        self.value = nn.Linear(config.d_model, config.d_model, bias=False)
        self.out = nn.Linear(config.d_model, config.d_model, bias=False)

    def _split(self, x: torch.Tensor) -> torch.Tensor:
        batch, length, _ = x.shape
        return x.view(batch, length, self.heads, self.head_dim).transpose(1, 2)

    def forward(self, x: torch.Tensor, context: torch.Tensor | None = None, mask: torch.Tensor | None = None,
                rotary: Rotary | None = None, causal: bool = False) -> torch.Tensor:
        source = x if context is None else context
        query, key, value = self._split(self.query(x)), self._split(self.key(source)), self._split(self.value(source))
        if rotary is not None:
            query, key = rotary(query), rotary(key)
        attended = F.scaled_dot_product_attention(
            query, key, value, attn_mask=mask, is_causal=causal,
            dropout_p=self.dropout if self.training else 0.0,
        )
        batch, _, length, _ = attended.shape
        return self.out(attended.transpose(1, 2).reshape(batch, length, -1))


class FeedForward(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.up = nn.Linear(config.d_model, config.d_ff, bias=False)
        self.down = nn.Linear(config.d_ff, config.d_model, bias=False)
        self.dropout = nn.Dropout(config.dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.down(self.dropout(F.gelu(self.up(x))))


class EncoderLayer(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.attention_norm, self.attention = RMSNorm(config.d_model), Attention(config)
        self.ff_norm, self.ff = RMSNorm(config.d_model), FeedForward(config)
        self.dropout = nn.Dropout(config.dropout)

    def forward(self, x: torch.Tensor, mask: torch.Tensor, rotary: Rotary) -> torch.Tensor:
        x = x + self.dropout(self.attention(self.attention_norm(x), mask=mask, rotary=rotary))
        return x + self.dropout(self.ff(self.ff_norm(x)))


class DecoderLayer(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.self_norm, self.self_attention = RMSNorm(config.d_model), Attention(config)
        self.cross_norm, self.cross_attention = RMSNorm(config.d_model), Attention(config)
        self.ff_norm, self.ff = RMSNorm(config.d_model), FeedForward(config)
        self.dropout = nn.Dropout(config.dropout)

    def forward(self, x: torch.Tensor, memory: torch.Tensor, memory_mask: torch.Tensor, rotary: Rotary) -> torch.Tensor:
        x = x + self.dropout(self.self_attention(self.self_norm(x), rotary=rotary, causal=True))
        x = x + self.dropout(self.cross_attention(self.cross_norm(x), context=memory, mask=memory_mask))
        return x + self.dropout(self.ff(self.ff_norm(x)))


class Seq2SeqTransformer(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.config = config
        self.gradient_checkpointing = False
        self.embedding = nn.Embedding(config.vocab_size, config.d_model)
        self.rotary = Rotary(config.d_model // config.n_heads, config.max_positions)
        self.encoder = nn.ModuleList(EncoderLayer(config) for _ in range(config.encoder_layers))
        self.decoder = nn.ModuleList(DecoderLayer(config) for _ in range(config.decoder_layers))
        self.encoder_norm, self.decoder_norm = RMSNorm(config.d_model), RMSNorm(config.d_model)
        self.input_dropout = nn.Dropout(config.dropout)
        self._init_weights()

    def _init_weights(self) -> None:
        nn.init.normal_(self.embedding.weight, std=1.0)
        residual_std = 0.02 / math.sqrt(2 * (self.config.encoder_layers + self.config.decoder_layers))
        for name, module in self.named_modules():
            if isinstance(module, nn.Linear):
                is_residual_output = name.endswith(".out") or name.endswith(".down")
                nn.init.normal_(module.weight, std=residual_std if is_residual_output else 0.02)

    def parameter_count(self) -> int:
        return sum(parameter.numel() for parameter in self.parameters())

    def _run(self, layer: nn.Module, *args: torch.Tensor | Rotary) -> torch.Tensor:
        if self.gradient_checkpointing and self.training:
            return checkpoint(layer, *args, use_reentrant=False)
        return layer(*args)

    def encode(self, input_ids: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Encoder states and the key mask (batch, 1, 1, length) that hides padding."""
        mask = (input_ids != self.config.pad_id)[:, None, None, :]
        x = self.input_dropout(self.embedding(input_ids))
        for layer in self.encoder:
            x = self._run(layer, x, mask, self.rotary)
        return self.encoder_norm(x), mask

    def decode(self, decoder_input_ids: torch.Tensor, memory: torch.Tensor, memory_mask: torch.Tensor) -> torch.Tensor:
        x = self.input_dropout(self.embedding(decoder_input_ids))
        for layer in self.decoder:
            x = self._run(layer, x, memory, memory_mask, self.rotary)
        x = self.decoder_norm(x)
        return (x @ self.embedding.weight.t()) * (self.config.d_model ** -0.5)

    def shift_right(self, labels: torch.Tensor) -> torch.Tensor:
        """Decoder inputs: the target moved one step right, starting with the pad token as in T5."""
        shifted = labels.new_full(labels.shape, self.config.pad_id)
        shifted[:, 1:] = labels[:, :-1]
        return shifted.masked_fill(shifted == IGNORE_INDEX, self.config.pad_id)

    def forward(self, input_ids: torch.Tensor, labels: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Logits and mean cross-entropy over target tokens (labels equal to IGNORE_INDEX are skipped)."""
        memory, memory_mask = self.encode(input_ids)
        logits = self.decode(self.shift_right(labels), memory, memory_mask)
        loss = F.cross_entropy(logits.float().view(-1, logits.shape[-1]), labels.reshape(-1), ignore_index=IGNORE_INDEX)
        return logits, loss

    @torch.no_grad()
    def generate_greedy(self, input_ids: torch.Tensor, max_new_tokens: int = 64) -> torch.Tensor:
        """Greedy decoding. Simple and exact; fast KV-cached beam search comes with the generation pipeline."""
        memory, memory_mask = self.encode(input_ids)
        batch = input_ids.shape[0]
        output = input_ids.new_full((batch, 1), self.config.pad_id)
        finished = torch.zeros(batch, dtype=torch.bool, device=input_ids.device)
        for _ in range(max_new_tokens):
            next_token = self.decode(output, memory, memory_mask)[:, -1].argmax(-1)
            next_token = next_token.masked_fill(finished, self.config.pad_id)
            output = torch.cat([output, next_token[:, None]], dim=1)
            finished |= next_token == self.config.eos_id
            if finished.all():
                break
        return output[:, 1:]
