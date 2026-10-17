"""Expose only the current token's logits from the formula decoder graph."""

from pathlib import Path
from typing import Any, cast

from ..vendor import onnx_ml_pb2

# Protobuf builds these classes from its descriptor at import time.
onnx = cast(Any, onnx_ml_pb2)


def last_token_decoder(model_path: Path) -> bytes:
    """Transform a verified decoder in memory without changing stored weights."""
    model = onnx.ModelProto()
    model.ParseFromString(model_path.read_bytes())
    graph = model.graph
    if len(graph.output) != 1 or len(graph.output[0].type.tensor_type.shape.dim) != 3:
        raise ValueError("Formula decoder must output [batch, sequence, vocabulary]")
    output = graph.output[0]
    names = {name for node in graph.node for name in (*node.input, *node.output)}
    names.update(value.name for value in graph.initializer)
    index_name, output_name = "mathcraft_last_token_index", "mathcraft_step_logits"
    if {index_name, output_name} & names:
        raise ValueError("Formula decoder uses reserved step-output names")
    graph.initializer.add(
        name=index_name, data_type=onnx.TensorProto.INT64, int64_data=[-1]
    )
    gather = graph.node.add(op_type="Gather", name="mathcraft_last_token")
    gather.input.extend((output.name, index_name))
    gather.output.append(output_name)
    gather.attribute.add(name="axis", i=1, type=onnx.AttributeProto.INT)
    output.name = output_name
    del output.type.tensor_type.shape.dim[1]
    return model.SerializeToString()
