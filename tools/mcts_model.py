"""Optional Kaggle model and feature encoders from the MCTS sample.

This module is intentionally safe to import without PyTorch or the competition
``cg`` package.  ``MyModel`` loads PyTorch only when instantiated, and the
encoders use the current cg observation object's attributes without importing
its Linux-only enums.  They are intended for Linux/Kaggle experimentation;
training and evaluation must run in an environment containing the current cg
API and its ``libcg.so``.

The vocabulary sizes are API-dependent.  Obtain ``ModelConfig`` with
``from_cg_api()`` in Kaggle rather than copying sizes between API versions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .mcts_adapter import SparseVector


@dataclass(frozen=True)
class ModelConfig:
    card_count: int
    attack_count: int
    num_words_encoder: int = 24
    encoder_size: int = 22000
    decoder_main_feature: int = 8
    recover_special_condition: int = 0

    @property
    def decoder_attack_offset(self) -> int:
        return 14

    @property
    def decoder_card_offset(self) -> int:
        return self.decoder_attack_offset + self.attack_count

    @property
    def decoder_size(self) -> int:
        return self.decoder_card_offset + (
            1 + self.decoder_main_feature + self.recover_special_condition
        ) * self.card_count


def from_cg_api() -> ModelConfig:
    """Build vocabulary sizes from the installed Kaggle cg API (lazy import)."""
    from cg.api import SelectContext, all_attack, all_card_data  # type: ignore

    cards = all_card_data()
    attacks = all_attack()
    if not cards or not attacks:
        raise ValueError("cg API returned no cards or attacks")
    return ModelConfig(
        card_count=max(_id(x, "cardId") for x in cards) + 1,
        attack_count=max(_id(x, "attackId") for x in attacks) + 1,
        recover_special_condition=int(SelectContext.RECOVER_SPECIAL_CONDITION),
    )


def _id(obj: Any, name: str = "id") -> int:
    value = getattr(obj, name, None)
    if value is None:
        value = getattr(obj, "id", None)
    if value is None:
        raise ValueError(f"object has no {name}/id field")
    return int(value)


def _enum_name(value: Any) -> str:
    return str(getattr(value, "name", value)).split(".")[-1].upper()


def _card_id(card: Any) -> int:
    return _id(card)


def add_card(sv: SparseVector, card: Any | None, config: ModelConfig) -> None:
    if card is not None:
        sv.add(_card_id(card), 1)
    sv.advance(config.card_count)


def add_cards(sv: SparseVector, cards: Iterable[Any] | None, value: float, config: ModelConfig) -> None:
    if cards is not None:
        for card in cards:
            sv.add(_card_id(card), value)
    sv.advance(config.card_count)


def add_pokemon(sv: SparseVector, pokemon: Any | None, config: ModelConfig) -> None:
    if pokemon is None:
        sv.add_single(1)
        sv.advance(1 + 3 * config.card_count)
        return
    sv.add_single(0)
    sv.add_single(float(getattr(pokemon, "hp")) / 400)
    add_card(sv, pokemon, config)
    add_cards(sv, getattr(pokemon, "tools", None), 1.0, config)
    add_cards(sv, getattr(pokemon, "energyCards", None), 0.5, config)


def add_player(sv: SparseVector, player: Any, config: ModelConfig) -> None:
    sv.add_single(float(player.deckCount) / 60)
    sv.add_single(len(player.discard) / 60)
    sv.add_single(float(player.handCount) / 8)
    sv.add_single(len(player.bench) / 5)
    sv.add(len(player.prize), 1)
    sv.advance(7)
    for name in ("poisoned", "burned", "asleep", "paralyzed", "confused"):
        sv.add_single(getattr(player, name))
    add_cards(sv, player.discard, 0.25, config)


def get_encoder_input(obs: Any, your_deck: list[int], config: ModelConfig) -> SparseVector:
    """Encode a current cg ``Observation`` using the sample's 24 words."""
    your = int(obs.current.yourIndex)
    state = obs.current
    sv = SparseVector()
    for player_order in range(2):
        player = state.players[player_order ^ your]
        for bench_index in range(8):
            sv.word_start(); position = sv.position
            add_pokemon(sv, player.bench[bench_index] if bench_index < len(player.bench) else None, config)
            if bench_index != 7:
                sv.position = position
    for player_order in range(2):
        player = state.players[player_order ^ your]
        sv.word_start(); add_pokemon(sv, player.active[0] if player.active else None, config)
    for player_order in range(2):
        sv.word_start(); add_player(sv, state.players[player_order ^ your], config)
    sv.word_start(); add_cards(sv, state.players[your].hand, 0.25, config)
    sv.word_start()
    for card_id in your_deck:
        sv.add(int(card_id), 0.25)
    sv.advance(config.card_count)
    sv.word_start(); add_cards(sv, state.stadium, 1.0, config)
    sv.word_start()
    sv.add_single(1); sv.add_single(state.turn / 10); sv.add_single(state.firstPlayer == your)
    return sv


def _get_card(obs: Any, area: Any, index: int, player_index: int) -> Any | None:
    player = obs.current.players[player_index]
    area_name = _enum_name(area)
    sources = {"DECK": obs.select.deck, "HAND": player.hand, "DISCARD": player.discard,
               "ACTIVE": player.active, "BENCH": player.bench, "PRIZE": player.prize,
               "STADIUM": obs.current.stadium, "LOOKING": obs.current.looking}
    source = sources.get(area_name)
    return None if source is None else source[index]


def get_decoder_input(obs: Any, actions: list[list[int]], config: ModelConfig) -> SparseVector:
    """Encode candidate action combinations; matches the sample's feature IDs."""
    sv = SparseVector(); your = int(obs.current.yourIndex); player = obs.current.players[your]
    context = int(obs.select.context)
    def add_card_feature(feature: int, card: Any | None) -> None:
        if card is not None:
            sv.add(config.decoder_card_offset + feature * config.card_count + _card_id(card), 1)
    for action in actions:
        sv.word_start()
        if not action:
            sv.add(0, 1); continue
        for index in action:
            option = obs.select.option[index]; kind = _enum_name(option.type)
            if kind == "END": sv.add(1, 1)
            elif kind == "YES": sv.add(2, 1)
            elif kind == "NO": sv.add(3, 1)
            elif kind == "SPECIAL_CONDITION": sv.add(4 + int(option.specialConditionType), 1)
            elif kind == "NUMBER": sv.add(9 + min(int(option.number), 4), 1)
            elif kind == "ATTACK": sv.add(config.decoder_attack_offset + int(option.attackId), 1)
            elif kind == "PLAY": sv.add(config.decoder_card_offset + _card_id(player.hand[option.index]), 1)
            elif kind in {"ATTACH", "EVOLVE"}:
                base = 1 if kind == "ATTACH" else 3
                add_card_feature(base, _get_card(obs, option.area, option.index, your))
                add_card_feature(base + 1, _get_card(obs, option.inPlayArea, option.inPlayIndex, your))
            elif kind in {"ABILITY", "DISCARD", "RETREAT"}:
                feature = {"ABILITY": 5, "DISCARD": 6, "RETREAT": 7}[kind]
                card = player.active[0] if kind == "RETREAT" else _get_card(obs, option.area, option.index, your)
                add_card_feature(feature, card)
            elif kind == "CARD":
                card = _get_card(obs, option.area, option.index, option.playerIndex)
                if card is not None: sv.add(config.decoder_card_offset + (config.decoder_main_feature + context) * config.card_count + _card_id(card), 1)
            elif kind in {"SKILL"}:
                sv.add(config.decoder_card_offset + (config.decoder_main_feature + context) * config.card_count + int(option.cardId), 1)
            # TOOL_CARD and ENERGY variants are API-specific; resolve their nested card.
            elif kind in {"TOOL_CARD", "ENERGY_CARD", "ENERGY"}:
                card = _get_card(obs, option.area, option.index, option.playerIndex)
                nested = card.tools[option.toolIndex] if kind == "TOOL_CARD" else card.energyCards[option.energyIndex]
                sv.add(config.decoder_card_offset + (config.decoder_main_feature + context) * config.card_count + _card_id(nested), 1)
    return sv


def eval_nn(encoder: SparseVector, decoder: SparseVector, model: Any) -> tuple[float, list[float]]:
    """Run a model without importing torch until evaluation is actually called."""
    import torch  # type: ignore
    device = next(model.parameters()).device
    value, policy = model(*[torch.tensor(x, dtype=torch.int32 if name == "index" or name == "offset" else torch.float32, device=device)
                            for name, x in (("index", encoder.index), ("value", encoder.value), ("offset", encoder.offset),
                                            ("index", decoder.index), ("value", decoder.value), ("offset", decoder.offset))])
    return float(value.tolist()[0][0]), policy.tolist()[0]


def _torch_model_class():
    import torch
    import torch.nn.functional as F
    class DecoderLayer(torch.nn.Module):
        def __init__(self, d_model, num_heads, d_feedforward):
            super().__init__(); self.attention = torch.nn.MultiheadAttention(d_model, num_heads)
            self.fc1 = torch.nn.Linear(d_model, d_feedforward); self.fc2 = torch.nn.Linear(d_feedforward, d_model)
            self.norm1 = torch.nn.LayerNorm(d_model); self.norm2 = torch.nn.LayerNorm(d_model)
        def forward(self, x, encoder_out):
            y, _ = self.attention(x, encoder_out, encoder_out, need_weights=False)
            y = self.norm1(x + y); return self.norm2(y + self.fc2(F.relu(self.fc1(y))))
    class MyModel(torch.nn.Module):
        def __init__(self, config, d_model=128, num_heads=2, d_feedforward=256, num_layers_encoder=1, num_layers_decoder=1):
            super().__init__(); self.config = config
            self.encoder_bag = torch.nn.EmbeddingBag(config.encoder_size, d_model, mode="sum")
            layer = torch.nn.TransformerEncoderLayer(d_model, num_heads, d_feedforward, 0)
            self.encoder = torch.nn.TransformerEncoder(layer, num_layers_encoder, enable_nested_tensor=False)
            self.encoder_fc = torch.nn.Linear(d_model, 1); self.decoder_bag = torch.nn.EmbeddingBag(config.decoder_size, d_model, mode="sum")
            self.decoder = torch.nn.ModuleList([DecoderLayer(d_model, num_heads, d_feedforward) for _ in range(num_layers_decoder)])
            self.decoder_fc = torch.nn.Linear(d_model, 1); self.d_model = d_model
        def forward(self, ie, ve, oe, id, vd, od):
            v = self.encoder_bag(ie, oe, ve).reshape(-1, self.config.num_words_encoder, self.d_model).transpose(0, 1)
            batch = v.size(1); encoded = self.encoder(v); value = torch.tanh(self.encoder_fc(encoded).mean(0))
            policy = self.decoder_bag(id, od, vd).reshape(batch, -1, self.d_model).transpose(0, 1)
            for layer in self.decoder: policy = layer(policy, encoded)
            return value, torch.tanh(self.decoder_fc(policy).transpose(0, 1).view(batch, -1))
    return MyModel


class MyModel:
    """Lazy PyTorch facade; constructing it is the point where torch is required."""
    def __new__(cls, config: ModelConfig, *args: Any, **kwargs: Any) -> Any:
        return _torch_model_class()(config, *args, **kwargs)
