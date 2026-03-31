# LaTeXSnipper 2.2 External Model Plan

## Goal

LaTeXSnipper 2.2 adds an `external_model` recognition path for local multimodal OCR models without refactoring the existing `pix2text` pipeline.

This version is deliberately conservative:

1. keep current `pix2text` logic working as-is
2. add a new independent external-model path
3. provide clear setup guidance in the settings page
4. keep the code boundary easy to maintain


## Why This Scope

The current desktop app already has a working `pix2text` flow in the main PyQt path.

For 2.2, the requirement is not to redesign the recognition system. The requirement is to let users connect better local multimodal OCR models such as:

- Qwen-VL-OCR
- Qwen2-VL / Qwen3-VL
- GOT-OCR 2.0
- GLM-OCR
- PaddleOCR-VL
- MinerU-like local services
- Ollama-hosted vision models

At the same time, the integration risk must stay low.

Therefore 2.2 should avoid:

- changing `src/backend/model.py`
- changing the old `pix2text` warmup and worker semantics
- touching deprecated Tauri or daemon-side architecture
- forcing all future models into one hardcoded model list


## Product Positioning

### Existing Path

`pix2text` remains the built-in compatibility path for screenshot and formula recognition.

### New Path

`external_model` becomes a user-configurable local API path for stronger multimodal OCR.

The product language should be:

- built-in recognition: `pix2text`
- external recognition: `外部模型...`

The user should understand that `外部模型...` is not one fixed model. It is an entry for connecting a local API service.


## Core Principle

2.2 should be implemented as a parallel path, not a rewrite.

That means:

- `pix2text` keeps using the current code path
- `external_model` uses its own config, client, worker, and error handling
- the two paths meet only at the UI selection layer and final recognition-result insertion layer


## Scope

### In Scope

- add `外部模型...` to the recognition model dropdown
- add a dedicated settings UI for external-model configuration
- support local HTTP API based recognition
- support at least two protocol types:
  - OpenAI-compatible
  - Ollama
- add guided onboarding so users know how to configure it
- keep `pix2text` unchanged

### Out of Scope for 2.2

- refactoring `src/backend/model.py`
- unifying all recognition backends under one new abstraction layer
- daemon / Tauri integration work
- automatic model installation
- deep PDF parsing redesign
- MinerU-specific pipeline integration
- hardcoding many model vendors into the main dropdown


## UX Plan

### Recognition Model Dropdown

The settings page recognition-model dropdown should contain only:

- `pix2text - 兼容模式`
- `外部模型...`

This keeps the product understandable and prevents dropdown bloat.

### Behavior When `pix2text` Is Selected

- keep the current `pix2text` UI visible
- keep `pix2text` mode selection visible
- keep current warmup and readiness semantics

### Behavior When `外部模型...` Is Selected

- hide `pix2text`-specific controls
- show a dedicated external-model configuration card
- show current configuration summary
- show setup guidance and a test-connection entry point


## Guided Onboarding Requirement

This is the most important UX part of 2.2.

If the user selects `外部模型...` and no valid config exists, the app must not leave the user in an unclear state.

The settings UI should immediately show:

1. what this feature is
2. what local service types are supported
3. what fields must be filled
4. how to verify the service is reachable
5. what typical model names look like

### Recommended Guidance Block

Suggested guidance copy:

- `外部模型用于连接本机或局域网中的多模态 OCR / VLM 服务。`
- `推荐协议：OpenAI 兼容接口、Ollama。`
- `请先在本地启动模型服务，再填写地址与模型名。`
- `若不确定，可先使用推荐预设自动填入示例配置。`

### Recommended First-Run Flow

When `外部模型...` is selected for the first time:

1. open the external-model section automatically
2. show a short introduction card
3. default to a recommended protocol preset
4. provide one-click preset fill
5. expose `测试连接`
6. if test fails, show actionable error text instead of raw stack output


## Recommended Settings Fields

The external-model settings area should contain:

- `协议`
  - `OpenAI-compatible`
  - `Ollama`
- `Base URL`
- `模型名`
- `API Key`
- `超时(秒)`
- `输出偏好`
  - `LaTeX 优先`
  - `Markdown`
  - `纯文本`
- `系统提示词 / 识别提示词`
- `测试连接`
- `使用推荐预设`

### Recommended Presets

Presets should not be the main architecture. They should only fill forms.

Recommended initial presets:

- `GLM-OCR`
- `PaddleOCR-VL`
- `Qwen2.5-VL / Qwen3-VL`
- `Ollama Vision`

Each preset should only populate:

- protocol
- base URL example
- model name example
- prompt template
- output preference


## Proposed Project Structure

2.2 should introduce a dedicated external-model domain under `src/backend/external_model`.

Recommended structure:

```text
src/
  main.py
  settings_window.py

  backend/
    model.py
    external_model/
      __init__.py
      client.py
      worker.py
      presets.py
      prompts.py
      schemas.py
      errors.py
```

### Module Responsibilities

#### `src/backend/external_model/client.py`

Responsible for:

- building HTTP requests
- adapting protocol differences
- converting image input to request payload
- parsing response into a normalized result

This module should not know about PyQt widgets.

#### `src/backend/external_model/worker.py`

Responsible for:

- running external recognition off the UI thread
- timeout control
- success / error signal emission

This module should mirror the existing worker style used by the desktop app, but remain independent from `pix2text`.

#### `src/backend/external_model/presets.py`

Responsible for:

- storing preset definitions
- filling default form values
- keeping vendor-specific examples out of `main.py`

#### `src/backend/external_model/prompts.py`

Responsible for:

- storing recommended prompt templates
- separating recognition prompt tuning from UI code

#### `src/backend/external_model/schemas.py`

Responsible for:

- defining normalized config payload
- defining normalized recognition result payload

#### `src/backend/external_model/errors.py`

Responsible for:

- defining user-facing error categories
- mapping raw request errors into concise messages


## Integration Strategy

### Keep Existing `pix2text` Path

Do not change:

- `src/backend/model.py`
- existing `pix2text` warmup logic
- existing `pix2text` mode mapping
- existing PDF logic unless required for basic branching

### Add a New Branch in Main Flow

`src/main.py` should only gain a small branch:

1. detect whether current selection is `pix2text` or `external_model`
2. if `pix2text`, keep old logic
3. if `external_model`, dispatch to the new worker

This keeps blast radius small.


## Configuration Strategy

External-model config should remain independent from `pix2text` config.

Recommended config keys:

```json
{
  "default_model": "pix2text",
  "external_model_enabled": false,
  "external_model_provider": "openai_compatible",
  "external_model_base_url": "http://127.0.0.1:11434",
  "external_model_model_name": "",
  "external_model_api_key": "",
  "external_model_timeout_sec": 60,
  "external_model_output_mode": "latex",
  "external_model_prompt_template": "ocr_formula_v1",
  "external_model_preset": ""
}
```

Important:

- do not mix these values into `pix2text_mode`
- do not reuse `pix2text` readiness flags
- do not let `external_model` pretend to be a `pix2text_*` variant


## Protocol Support

2.2 should support only two protocol families.

### 1. OpenAI-Compatible

Used for:

- local OpenAI-compatible OCR/VLM services
- vLLM-like deployments
- SGLang-like deployments
- other compatible wrappers

### 2. Ollama

Used for:

- locally hosted vision-capable Ollama models

This is enough for 2.2. More providers should be added later only when they require real protocol differences.


## Result Normalization

External models will return inconsistent payloads. The app should normalize results early.

Recommended normalized result shape:

```python
{
    "text": "...",
    "latex": "...",
    "markdown": "...",
    "backend": "external_model",
    "provider": "ollama",
    "model_name": "qwen2.5vl:7b",
    "raw": {...}
}
```

The desktop UI should consume this normalized result instead of provider-specific response formats.


## Validation and Error UX

The settings page should include `测试连接`.

Validation checks should include:

- URL format is valid
- protocol type is selected
- model name is not empty
- service responds within timeout

Recommended user-facing error messages:

- `无法连接到本地服务，请确认服务已启动。`
- `模型名为空，请填写本地服务中可用的模型名称。`
- `接口返回格式不受支持，请切换协议或检查模型服务。`
- `识别超时，请提高超时设置或更换更轻量的模型。`

Avoid exposing raw traceback in the normal setup flow.


## Main Window Behavior

When external model is selected:

- do not run `pix2text` warmup
- do not display `pix2text`-specific loading messages
- display a backend-specific status such as:
  - `外部模型未配置`
  - `外部模型待测试`
  - `外部模型已就绪`
  - `外部模型识别中...`

If the user starts recognition without a valid config:

- interrupt the action
- open or focus the settings guidance
- show a direct message telling the user what is missing


## Suggested Development Phases

### Phase 1: Infrastructure

- create `src/backend/external_model`
- add config read/write helpers
- add client and worker skeleton
- define normalized result and error model

### Phase 2: Settings UI

- add `外部模型...` dropdown item
- add configuration area
- add guidance card
- add preset fill
- add `测试连接`

### Phase 3: Main-Flow Branching

- branch recognition entry in `src/main.py`
- integrate worker callbacks
- map normalized result into existing result insertion flow

### Phase 4: Polish

- improve prompt templates
- improve error messages
- add recommended preset copy
- add status summary text in settings page


## Risks and Mitigations

### Risk 1: Users do not know how to configure local services

Mitigation:

- make guidance first-class in settings
- include presets and examples
- provide `测试连接`

### Risk 2: External model outputs are inconsistent

Mitigation:

- normalize results in `client.py`
- keep prompt templates centralized

### Risk 3: Regression in existing `pix2text` flow

Mitigation:

- do not modify `src/backend/model.py`
- use a separate worker and separate config keys
- keep branching shallow in `src/main.py`

### Risk 4: Scope creep into full recognition refactor

Mitigation:

- explicitly keep 2.2 as a parallel-path release
- defer unified backend abstraction to a later version if needed


## Non-Goals Reminder

2.2 is not the version to:

- redesign all recognition architecture
- merge external model and `pix2text` internals
- support every OCR engine with dedicated code
- overhaul PDF recognition

The correct outcome is simpler:

`pix2text` remains stable, and users who want stronger OCR can connect a local external model through a well-guided settings flow.


## Final Recommendation

For 2.2, the best maintainable plan is:

1. add `src/backend/external_model`
2. keep `pix2text` untouched
3. add exactly one new dropdown entry: `外部模型...`
4. make configuration guidance a first-class UX feature
5. support only `OpenAI-compatible` and `Ollama` protocols in the first release

This gives users a practical upgrade path without destabilizing the current desktop codebase.
