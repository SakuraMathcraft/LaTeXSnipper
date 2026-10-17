"""Formula decoding preserves results while reusing device-resident activations."""

import sys
from types import SimpleNamespace

import numpy as np
import pytest

from mathcraft_ocr.adapters.formula_inference import encode_formula
from mathcraft_ocr.adapters.formula_recognizer import _generate_formula_tokens


class DeviceValue:
    def __init__(self, array, device_id=0):
        self.array = array
        self.device_id = device_id
        self.downloads = 0

    def shape(self):
        return self.array.shape

    def numpy(self):
        self.downloads += 1
        return self.array.copy()


class Binding:
    def __init__(self):
        self.inputs = {}
        self.outputs = []
        self.output_shape = None
        self.device_id = None

    def bind_cpu_input(self, name, value):
        self.inputs[name] = value

    def bind_ortvalue_input(self, name, value):
        self.inputs[name] = value

    def bind_output(self, _name, device, device_id=0):
        self.device_id = device_id if device == "cuda" else None

    def clear_binding_outputs(self):
        self.outputs.clear()
        self.output_shape = None

    def get_outputs(self):
        return self.outputs


class DecoderSession:
    def __init__(self, finish_after):
        self.finish_after = finish_after
        self.batch_sizes = []
        self.activation_values = []

    def get_inputs(self):
        return [SimpleNamespace(name=name) for name in ("ids", "hidden")]

    def get_outputs(self):
        return [SimpleNamespace(name="logits")]

    def io_binding(self):
        return Binding()

    def run(self, _outputs, inputs):
        ids, hidden = inputs["ids"], inputs["hidden"]
        self.batch_sizes.append(len(ids))
        logits = np.full((*ids.shape, 10), -20.0, dtype=np.float32)
        for row, original in enumerate(hidden[:, 0, 0].astype(int)):
            token = 9 if ids.shape[1] >= self.finish_after[original] else original + 2
            logits[row, -1, token] = 20.0
        return [logits]

    def run_with_iobinding(self, binding):
        hidden = binding.inputs["hidden"]
        self.activation_values.append(hidden)
        output = self.run(None, {"ids": binding.inputs["ids"], "hidden": hidden.array})[
            0
        ]
        # Dynamic outputs must not retain an earlier prefix or batch shape.
        if binding.output_shape is not None:
            assert binding.output_shape == output.shape
        binding.output_shape = output.shape
        binding.outputs = [DeviceValue(output)]


@pytest.mark.parametrize("finish_after", [(2, 4), (4, 2), (3, 3), (5, 3, 2)])
def test_cuda_matches_cpu_when_different_sequences_finish(monkeypatch, finish_after):
    uploads = []

    def upload(array, device, device_id):
        assert device == "cuda" and device_id == 2
        value = DeviceValue(array, device_id)
        uploads.append(value)
        return value

    monkeypatch.setitem(
        sys.modules,
        "onnxruntime",
        SimpleNamespace(OrtValue=SimpleNamespace(ortvalue_from_numpy=upload)),
    )
    hidden = np.zeros((len(finish_after), 2, 3), dtype=np.float32)
    hidden[:, 0, 0] = np.arange(len(finish_after))
    initial = DeviceValue(hidden, 2)
    cpu, gpu = DecoderSession(finish_after), DecoderSession(finish_after)
    options = {"decoder_start_id": 1, "eos_id": 9, "max_new_tokens": 10}
    expected = _generate_formula_tokens(cpu, hidden, **options)
    actual = _generate_formula_tokens(gpu, initial, cuda_device_id=2, **options)
    assert actual[0] == expected[0]
    assert actual[1] == expected[1]
    np.testing.assert_array_equal(actual[2], expected[2])
    assert gpu.batch_sizes == cpu.batch_sizes
    # Crossing to the host is allowed only when rows actually disappear.
    shrink_count = len(set(gpu.batch_sizes)) - 1
    assert len(uploads) == shrink_count
    assert sum(value.downloads for value in [initial, *uploads]) == shrink_count
    assert gpu.activation_values[0] is gpu.activation_values[1]


def test_cuda_keeps_repetition_stop_and_token_limit(monkeypatch):
    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace())
    hidden = np.zeros((1, 2, 3), dtype=np.float32)
    options = {"decoder_start_id": 1, "eos_id": None, "max_new_tokens": 80}
    cpu = _generate_formula_tokens(DecoderSession((100,)), hidden, **options)
    gpu = _generate_formula_tokens(
        DecoderSession((100,)), DeviceValue(hidden), cuda_device_id=0, **options
    )
    assert gpu[0] == cpu[0]
    assert gpu[2].tolist() == cpu[2].tolist() == [True]
    limited = _generate_formula_tokens(
        DecoderSession((100,)),
        DeviceValue(hidden),
        cuda_device_id=0,
        **{**options, "max_new_tokens": 3},
    )
    assert limited[0] == [[2, 2, 2]]
    assert limited[2].tolist() == [False]


def test_encoder_cuda_output_stays_on_selected_device():
    class Encoder:
        def get_inputs(self):
            return [SimpleNamespace(name="pixels")]

        def get_outputs(self):
            return [SimpleNamespace(name="hidden")]

        def io_binding(self):
            return Binding()

        def run_with_iobinding(self, binding):
            binding.outputs = [DeviceValue(binding.inputs["pixels"], binding.device_id)]

    pixels = np.zeros((1, 3, 4), dtype=np.float32)
    result = encode_formula(Encoder(), pixels, 2)
    assert result.device_id == 2
    assert result.downloads == 0
    np.testing.assert_array_equal(result.array, pixels)
