"""Keep formula encoder activations on the device during autoregressive decoding."""

from __future__ import annotations

from typing import Any

import numpy as np


def encode_formula(session, pixel_values: np.ndarray, cuda_device_id: int | None):
    input_name = session.get_inputs()[0].name
    if cuda_device_id is None:
        return session.run(None, {input_name: pixel_values})[0]
    binding = session.io_binding()
    binding.bind_cpu_input(input_name, np.ascontiguousarray(pixel_values))
    binding.bind_output(session.get_outputs()[0].name, "cuda", cuda_device_id)
    session.run_with_iobinding(binding)
    return binding.get_outputs()[0]


class FormulaDecoder:
    def __init__(self, session, hidden_states, cuda_device_id: int | None):
        self.session = session
        self.hidden_states: Any = hidden_states
        self.cuda_device_id = cuda_device_id
        inputs = session.get_inputs()
        self.input_name, self.hidden_name = inputs[0].name, inputs[1].name
        self.binding = None
        if cuda_device_id is None:
            self.batch_size = hidden_states.shape[0]
        else:
            self.batch_size = hidden_states.shape()[0]
            self.binding = session.io_binding()
            self.binding.bind_ortvalue_input(self.hidden_name, hidden_states)
            self.output_name = session.get_outputs()[0].name

    def step(self, input_ids: np.ndarray) -> np.ndarray:
        if self.binding is None:
            logits = self.session.run(
                None,
                {self.input_name: input_ids, self.hidden_name: self.hidden_states},
            )[0]
        else:
            self.binding.bind_cpu_input(self.input_name, input_ids)
            # Prefix length changes every step, so an earlier output allocation
            # cannot be reused for the new logits shape.
            self.binding.clear_binding_outputs()
            self.binding.bind_output(self.output_name, "cpu")
            self.session.run_with_iobinding(self.binding)
            logits = self.binding.get_outputs()[0].numpy()
        return logits[:, -1, :]

    def retain(self, rows: list[int]) -> None:
        if len(rows) == self.batch_size:
            return
        if self.binding is None:
            self.hidden_states = self.hidden_states[rows]
        else:
            import onnxruntime as ort

            assert self.cuda_device_id is not None
            # Compact only when a sequence finishes. The usual decoding step
            # reuses the same device allocation without any activation upload.
            compact = np.ascontiguousarray(self.hidden_states.numpy()[rows])
            self.hidden_states = ort.OrtValue.ortvalue_from_numpy(
                compact, "cuda", self.cuda_device_id
            )
            self.binding.bind_ortvalue_input(self.hidden_name, self.hidden_states)
        self.batch_size = len(rows)
