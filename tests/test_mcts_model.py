"""Pure tests for the optional MCTS model support (no cg or torch required)."""

from dataclasses import dataclass

from tools.mcts_model import ModelConfig, add_pokemon
from tools.mcts_adapter import SparseVector


def test_model_config_derives_decoder_layout():
    config = ModelConfig(card_count=100, attack_count=7, recover_special_condition=2)
    assert config.decoder_attack_offset == 14
    assert config.decoder_card_offset == 21
    assert config.decoder_size == 21 + 11 * 100


@dataclass
class Pokemon:
    id: int = 12
    hp: int = 200
    tools: list = None
    energyCards: list = None


def test_empty_pokemon_keeps_fixed_feature_width():
    vector = SparseVector()
    add_pokemon(vector, None, ModelConfig(card_count=10, attack_count=2))
    assert vector.index == [0]
    assert vector.position == 32


def test_pokemon_encoder_uses_card_and_normalized_hp():
    vector = SparseVector()
    add_pokemon(vector, Pokemon(), ModelConfig(card_count=10, attack_count=2),)
    assert vector.index == [1, 14]
    assert vector.value == [0.5, 1.0]
    assert vector.position == 32
