from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from semicon_alpha.utils.io import load_yaml


SignMode = Literal["use_edge_sign", "preserve", "invert", "mixed"]


class GraphBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EdgeTraversalRule(GraphBaseModel):
    forward_multiplier: float
    reverse_multiplier: float
    allows_reverse_traversal: bool = True
    forward_sign_mode: SignMode = "use_edge_sign"
    reverse_sign_mode: SignMode = "use_edge_sign"
    confidence_penalty: float = 1.0
    max_depth_preference: int = 3


class PropagationConfig(GraphBaseModel):
    max_depth: int = 3
    beam_width: int = 10
    top_paths_per_target: int = 3
    min_path_score: float = 0.02
    hop_decay: dict[int, float] = Field(default_factory=dict)


class GraphSchema(GraphBaseModel):
    version: str
    propagation: PropagationConfig
    edge_type_rules: dict[str, EdgeTraversalRule]


def load_graph_schema(path: Path) -> GraphSchema:
    payload = load_yaml(path)
    if "propagation" in payload and "hop_decay" in payload["propagation"]:
        payload["propagation"]["hop_decay"] = {
            int(key): value for key, value in payload["propagation"]["hop_decay"].items()
        }
    return GraphSchema(**payload)
