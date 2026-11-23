"""Token-step execution for the FP32, CPU INT8 and CUDA FP16 formula graphs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import numpy as np

from ..profiles import CUDA_PROVIDER, resolve_formula_variant
from ..providers import ProviderInfo
from .common import create_session

if TYPE_CHECKING:
    from onnxruntime import OrtValue


def load_formula_sessions(root: Path, provider: ProviderInfo, variant: str) -> tuple:
    encoder = create_session(root / "encoder_model.onnx", provider)
    if variant == "fp32":
        from .formula_model import last_token_decoder

        decoder = create_session(
            root / "decoder_model.onnx", provider, model_transform=last_token_decoder
        )
        return encoder, decoder
    projection = create_session(root / "decoder_cross_kv_model.onnx", provider)
    step = create_session(root / "decoder_with_past_model.onnx", provider)
    return encoder, projection, step


class TokenDecoder(Protocol):
    @property
    def compact(self) -> Callable[[np.ndarray], None] | None: ...

    def step(self, ids: np.ndarray, position: int) -> tuple[np.ndarray, np.ndarray]: ...


def _greedy_tokens(logits: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tokens = np.argmax(logits, axis=1)
    # The greedy token is the maximum logit, so its softmax numerator is one.
    confidence = np.reciprocal(
        np.exp(logits - logits[np.arange(len(tokens)), tokens, None]).sum(axis=1)
    )
    return tokens, confidence


class Fp32Decoder:
    def __init__(
        self, sessions: tuple, pixels: np.ndarray, device_id: int | None
    ) -> None:
        encoder, self.session = sessions
        self.device_id = device_id
        self.prefix = np.empty((len(pixels), 0), dtype=np.int64)
        self.input_name, self.hidden_name = [
            item.name for item in self.session.get_inputs()
        ]
        self.output_name = self.session.get_outputs()[0].name
        encoder_input = encoder.get_inputs()[0].name
        self.binding = None
        self.hidden: np.ndarray | OrtValue
        if device_id is None:
            self.hidden = encoder.run(None, {encoder_input: pixels})[0]
        else:
            io = encoder.io_binding()
            io.bind_cpu_input(encoder_input, pixels)
            io.bind_output(encoder.get_outputs()[0].name, "cuda", device_id)
            encoder.run_with_iobinding(io)
            self.hidden = io.get_outputs()[0]
            self.binding = self.session.io_binding()
            self.binding.bind_ortvalue_input(self.hidden_name, self.hidden)

    def step(self, ids: np.ndarray, position: int) -> tuple[np.ndarray, np.ndarray]:
        self.prefix = np.concatenate((self.prefix, ids), axis=1)
        if self.binding is None:
            logits = self.session.run(
                None, {self.input_name: self.prefix, self.hidden_name: self.hidden}
            )[0]
        else:
            self.binding.bind_cpu_input(self.input_name, self.prefix)
            self.binding.clear_binding_outputs()
            self.binding.bind_output(self.output_name, "cpu")
            self.session.run_with_iobinding(self.binding)
            logits = self.binding.get_outputs()[0].numpy()
        return _greedy_tokens(logits)

    def compact(self, rows: np.ndarray) -> None:
        self.prefix = self.prefix[rows]
        if self.binding is None:
            self.hidden = cast(np.ndarray, self.hidden)[rows]
        else:
            import onnxruntime as ort

            assert self.device_id is not None
            values = np.ascontiguousarray(cast(ort.OrtValue, self.hidden).numpy()[rows])
            self.hidden = ort.OrtValue.ortvalue_from_numpy(
                values, "cuda", self.device_id
            )
            self.binding.bind_ortvalue_input(self.hidden_name, self.hidden)


class CpuDecoder:
    def __init__(self, sessions: tuple, pixels: np.ndarray) -> None:
        encoder, projection, self.session = sessions
        hidden = encoder.run(None, {encoder.get_inputs()[0].name: pixels})[0]
        cross_cache = projection.run(None, {projection.get_inputs()[0].name: hidden})
        self.cache = {
            item.name: value
            for item, value in zip(projection.get_outputs(), cross_cache, strict=True)
        }
        batch = len(pixels)
        self.past_names = [
            value.name
            for value in self.session.get_inputs()
            if value.name.startswith("past_self_")
        ]
        for name in self.past_names:
            self.cache[name] = np.empty((batch, 8, 0, 32), dtype=np.float32)
        self.outputs = [
            "logits",
            *(name.replace("past_", "present_", 1) for name in self.past_names),
        ]

    def step(self, ids: np.ndarray, position: int) -> tuple[np.ndarray, np.ndarray]:
        logits, *present = self.session.run(
            self.outputs, {"input_ids": ids, **self.cache}
        )
        self.cache.update(zip(self.past_names, present, strict=True))
        return _greedy_tokens(logits)

    def compact(self, rows: np.ndarray) -> None:
        self.cache = {name: value[rows] for name, value in self.cache.items()}


class CudaDecoder:
    compact = None

    def __init__(self, sessions: tuple, pixels: np.ndarray, device_id: int) -> None:
        import onnxruntime as ort

        encoder, projection, self.session = sessions
        encoder_io = encoder.io_binding()
        encoder_io.bind_cpu_input(encoder.get_inputs()[0].name, pixels)
        encoder_io.bind_output(encoder.get_outputs()[0].name, "cuda", device_id)
        encoder.run_with_iobinding(encoder_io)

        projection_io = projection.io_binding()
        projection_io.bind_ortvalue_input(
            projection.get_inputs()[0].name, encoder_io.get_outputs()[0]
        )
        cross_names = [output.name for output in projection.get_outputs()]
        for name in cross_names:
            projection_io.bind_output(name, "cuda", device_id)
        projection.run_with_iobinding(projection_io)

        self.binding = self.session.io_binding()
        self.cross_cache = projection_io.get_outputs()
        for name, value in zip(cross_names, self.cross_cache, strict=True):
            self.binding.bind_ortvalue_input(name, value)

        batch = len(pixels)
        initial_cache = np.zeros((2, batch, 8, 512, 32), dtype=np.float16)
        self.self_cache = []
        for layer in range(6):
            value = ort.OrtValue.ortvalue_from_numpy(initial_cache, "cuda", device_id)
            self.self_cache.append(value)
            self.binding.bind_ortvalue_input(f"past_self.{layer}", value)
            self.binding.bind_ortvalue_output(f"present_self.{layer}", value)

        self.position = np.zeros(1, dtype=np.int32)
        self.tokens = np.empty((batch, 1), dtype=np.int64)
        self.confidence = np.empty(batch, dtype=np.float32)
        for name, buffer in (
            ("next_token", self.tokens),
            ("confidence", self.confidence),
        ):
            self.binding.bind_output(
                name, "cpu", 0, buffer.dtype, buffer.shape, buffer.ctypes.data
            )

    def step(self, ids: np.ndarray, position: int) -> tuple[np.ndarray, np.ndarray]:
        self.position[0] = position
        self.binding.bind_cpu_input("input_ids", ids)
        self.binding.bind_cpu_input("past_sequence_length", self.position)
        self.session.run_with_iobinding(self.binding)
        return self.tokens[:, 0], self.confidence


def formula_decoder(
    sessions: tuple, pixel_values: np.ndarray, provider: ProviderInfo, variant: str
) -> TokenDecoder:
    variant = resolve_formula_variant(provider.active_provider, variant)
    device_id = (
        int(provider.device_id or 0)
        if provider.active_provider == CUDA_PROVIDER
        else None
    )
    if variant == "cuda-fp16":
        pixels = np.ascontiguousarray(pixel_values, dtype=np.float16)
        assert device_id is not None
        return CudaDecoder(sessions, pixels, device_id)
    pixels = np.ascontiguousarray(pixel_values, dtype=np.float32)
    if variant == "fp32":
        return Fp32Decoder(sessions, pixels, device_id)
    return CpuDecoder(sessions, pixels)
