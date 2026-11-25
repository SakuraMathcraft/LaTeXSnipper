"""Token-step execution for the FP32, CPU INT8 and CUDA FP16 formula graphs."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import numpy as np

from ..profiles import CUDA_PROVIDER, FP32_V2, resolve_formula_variant
from ..providers import ProviderInfo
from .common import create_session

if TYPE_CHECKING:
    from onnxruntime import InferenceSession, OrtValue

logger = logging.getLogger(f"latexsnipper.{__name__}")


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
    def compact(self, rows: np.ndarray) -> bool: ...

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

    def compact(self, rows: np.ndarray) -> bool:
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
        return True


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

    def compact(self, rows: np.ndarray) -> bool:
        self.cache = {name: value[rows] for name, value in self.cache.items()}
        return True


@lru_cache(maxsize=8)
def _cuda_cache_row_session(
    device_id: int, cross_count: int, self_count: int, *, dynamic_fp32: bool = False
) -> InferenceSession:
    import onnxruntime as ort

    from .formula_model import cache_row_selection_model

    options = ort.SessionOptions()
    options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
    session = ort.InferenceSession(
        cache_row_selection_model(cross_count, self_count, dynamic_fp32=dynamic_fp32),
        sess_options=options,
        providers=[(CUDA_PROVIDER, {"device_id": device_id})],
        enable_fallback=False,
    )
    session.disable_fallback()
    return session


def _project_cuda_cache(encoder, projection, pixels: np.ndarray, device_id: int):
    encoder_io = encoder.io_binding()
    encoder_io.bind_cpu_input(encoder.get_inputs()[0].name, pixels)
    encoder_io.bind_output(encoder.get_outputs()[0].name, "cuda", device_id)
    encoder.run_with_iobinding(encoder_io)

    projection_io = projection.io_binding()
    projection_io.bind_ortvalue_input(
        projection.get_inputs()[0].name, encoder_io.get_outputs()[0]
    )
    names = [output.name for output in projection.get_outputs()]
    for name in names:
        projection_io.bind_output(name, "cuda", device_id)
    projection.run_with_iobinding(projection_io)
    return names, projection_io.get_outputs()


def _select_cuda_cache_rows(
    gather, device_id: int, rows: np.ndarray, caches: tuple[OrtValue, ...]
):
    binding = gather.io_binding()
    binding.bind_cpu_input("rows", rows)
    for index, value in enumerate(caches):
        binding.bind_ortvalue_input(f"cache_{index}", value)
        binding.bind_output(f"selected_{index}", "cuda", device_id)
    gather.run_with_iobinding(binding)
    return binding.get_outputs()


class CudaFp32Decoder:
    def __init__(self, sessions: tuple, pixels: np.ndarray, device_id: int) -> None:
        encoder, projection, self.session = sessions
        self.device_id = device_id
        self.cross_names, self.cross_cache = _project_cuda_cache(
            encoder, projection, pixels, device_id
        )
        self.past_names = [
            value.name
            for value in self.session.get_inputs()
            if value.name.startswith("past_self_")
        ]
        self.present_names = [
            name.replace("past_", "present_", 1) for name in self.past_names
        ]
        self.empty = np.empty((len(pixels), 8, 0, 32), dtype=np.float32)
        self.self_cache: list[OrtValue] = []

    def step(self, ids: np.ndarray, position: int) -> tuple[np.ndarray, np.ndarray]:
        import onnxruntime as ort

        binding = self.session.io_binding()
        binding.bind_cpu_input("input_ids", ids)
        for name, value in zip(self.cross_names, self.cross_cache, strict=True):
            binding.bind_ortvalue_input(name, value)
        if position == 0:
            for name in self.past_names:
                binding.bind_cpu_input(name, self.empty)
        else:
            for name, value in zip(self.past_names, self.self_cache, strict=True):
                binding.bind_ortvalue_input(name, value)
        binding.bind_output("logits", "cpu")
        shape = [len(ids), 8, position + 1, 32]
        present = [
            ort.OrtValue.ortvalue_from_shape_and_type(
                shape, np.float32, "cuda", self.device_id
            )
            for _ in self.present_names
        ]
        for name, value in zip(self.present_names, present, strict=True):
            binding.bind_ortvalue_output(name, value)
        self.session.run_with_iobinding(binding)
        self.self_cache = present
        return _greedy_tokens(binding.get_outputs()[0].numpy())

    def compact(self, rows: np.ndarray) -> bool:
        cross_count = len(self.cross_cache)
        caches = (*self.cross_cache, *self.self_cache)
        gather = _cuda_cache_row_session(
            self.device_id, cross_count, len(self.self_cache), dynamic_fp32=True
        )
        selected = _select_cuda_cache_rows(gather, self.device_id, rows, caches)
        self.cross_cache, self.self_cache = (
            selected[:cross_count],
            selected[cross_count:],
        )
        return True


class CudaDecoder:
    def __init__(self, sessions: tuple, pixels: np.ndarray, device_id: int) -> None:
        import onnxruntime as ort

        encoder, projection, self.session = sessions
        self.device_id = device_id
        self.cross_names, self.cross_cache = _project_cuda_cache(
            encoder, projection, pixels, device_id
        )
        initial_cache = np.zeros((2, len(pixels), 8, 512, 32), dtype=np.float16)
        self.self_cache = [
            ort.OrtValue.ortvalue_from_numpy(initial_cache, "cuda", device_id)
            for _ in range(6)
        ]
        self.position = np.zeros(1, dtype=np.int32)
        self.next_compaction = 16
        self.compaction_disabled = False
        self._bind_cache(len(pixels))

    def _bind_cache(self, batch: int) -> None:
        self.binding = self.session.io_binding()
        for name, value in zip(self.cross_names, self.cross_cache, strict=True):
            self.binding.bind_ortvalue_input(name, value)
        for layer, value in enumerate(self.self_cache):
            self.binding.bind_ortvalue_input(f"past_self.{layer}", value)
            self.binding.bind_ortvalue_output(f"present_self.{layer}", value)
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

    def compact(self, rows: np.ndarray) -> bool:
        position = int(self.position[0])
        if (
            self.compaction_disabled
            or position < self.next_compaction
            or len(rows) * 4 > len(self.tokens) * 3
        ):
            return False
        cross_count = len(self.cross_cache)
        gather = _cuda_cache_row_session(
            self.device_id, cross_count, len(self.self_cache)
        )
        try:
            selected = _select_cuda_cache_rows(
                gather, self.device_id, rows, (*self.cross_cache, *self.self_cache)
            )
        except Exception as exc:
            error = str(exc).lower()
            if not any(
                message in error
                for message in (
                    "out of memory",
                    "out_of_memory",
                    "failed to allocate memory",
                )
            ):
                raise
            logger.debug("Leaving finished formula rows in the batch: %s", exc)
            self.compaction_disabled = True
            return False
        self.cross_cache, self.self_cache = (
            selected[:cross_count],
            selected[cross_count:],
        )
        self.next_compaction = position + 12
        self._bind_cache(len(rows))
        return True


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
    if (
        variant == FP32_V2
        and provider.use_cuda
        and all(CUDA_PROVIDER in session.get_providers() for session in sessions)
    ):
        return CudaFp32Decoder(sessions, pixels, int(provider.device_id or 0))
    return CpuDecoder(sessions, pixels)
