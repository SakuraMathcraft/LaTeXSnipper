# coding: utf-8

from __future__ import annotations

from backend.mathcraft.diagnostics import classify_mathcraft_failure
from localization.manager import mark_for_translation, translate as tr


EXTERNAL_MODEL_BACKENDS = {"external_model", "ollama", "openai_compatible", "mineru"}

CANCELED_WORKER_MESSAGE = mark_for_translation("已取消")
EMPTY_RESULT_MESSAGE = mark_for_translation("识别结果为空")

_RECOGNITION_ERROR_MESSAGES = {
    "backend_unavailable": mark_for_translation(
        "外部模型尚未配置或当前不可用，请检查外部模型设置。"
    ),
    "backend_unsupported": mark_for_translation(
        "当前识别后端不受支持，请检查识别设置。"
    ),
    "canceled": mark_for_translation("识别已取消。"),
    "empty_content": mark_for_translation("未检测到可识别内容"),
    "empty_formula": mark_for_translation("未识别到公式内容"),
    "empty_text": mark_for_translation("未识别到文本内容"),
    "internal_error": mark_for_translation(
        "识别失败，请重试；若问题持续，请查看运行日志。"
    ),
    "invalid_backend": mark_for_translation("识别后端配置无效，请检查识别设置。"),
    "invalid_mode": mark_for_translation("当前识别模式不受支持，请检查识别设置。"),
    "model_unavailable": mark_for_translation(
        "MathCraft OCR 当前不可用，请等待模型加载完成后重试。"
    ),
    "queue_full": mark_for_translation("识别任务较多，请稍后重试。"),
    "timeout": mark_for_translation("识别超时，请稍后重试。"),
    "upstream_error": mark_for_translation(
        "外部模型调用失败，请检查服务状态和模型配置。"
    ),
    "upstream_timeout": mark_for_translation(
        "外部模型响应超时，请稍后重试或调整超时设置。"
    ),
}

EMPTY_CONTENT_MESSAGE = _RECOGNITION_ERROR_MESSAGES["empty_content"]
EMPTY_FORMULA_MESSAGE = _RECOGNITION_ERROR_MESSAGES["empty_formula"]
EMPTY_TEXT_MESSAGE = _RECOGNITION_ERROR_MESSAGES["empty_text"]

_IMAGE_INPUT_ERROR_MESSAGES = frozenset(
    (
        mark_for_translation("图片内容为空。"),
        mark_for_translation("图片尺寸超过安全限制。"),
        mark_for_translation("不支持该图片编码格式。"),
        mark_for_translation("图片尺寸超过安全解码限制。"),
        mark_for_translation("图片数据已损坏或不完整。"),
        mark_for_translation("图片文件超过大小限制。"),
        mark_for_translation("图片数据已损坏或格式不受支持。"),
        mark_for_translation("无法读取图片文件。"),
        mark_for_translation("内部图片必须为 RGB 格式。"),
        mark_for_translation("无法读取 Qt 图片数据。"),
    )
)

_MATHCRAFT_DIAGNOSTIC_TEXTS = (
    mark_for_translation("模型预热未完成"),
    mark_for_translation("MathCraft OCR 预热失败，请打开运行日志查看具体原因。"),
    mark_for_translation("MathCraft OCR 预热失败，将在首次识别时重试"),
    mark_for_translation("MathCraft OCR 模型未部署或加载失败。"),
    mark_for_translation("缺少 MathCraft OCR"),
    mark_for_translation("未找到 MathCraft OCR 包，请检查程序文件是否完整。"),
    mark_for_translation("缺少 onnxruntime"),
    mark_for_translation("未安装 onnxruntime 依赖，请重新校验依赖层是否安装完整。"),
    mark_for_translation("onnxruntime 依赖异常"),
    mark_for_translation("MathCraft 依赖不完整"),
    mark_for_translation(
        "当前依赖环境缺少 MathCraft OCR 运行依赖，请通过依赖管理安装 BASIC、CORE "
        "和对应的 MATHCRAFT_CPU/GPU 层。"
    ),
    mark_for_translation("模型缓存不完整"),
    mark_for_translation("MathCraft OCR 模型缓存不完整，请补齐模型权重后重试。"),
    mark_for_translation("模型权重下载失败"),
    mark_for_translation("MathCraft OCR 模型权重下载失败，请检查网络连接或稍后重试。"),
    mark_for_translation("OCR 字典与模型不匹配"),
    mark_for_translation(
        "MathCraft 文字识别模型与字典不匹配，请更新或重新下载 MathCraft 模型权重。"
    ),
    mark_for_translation("CUDA 环境异常"),
    mark_for_translation("CUDA 环境异常，GPU 推理不可用。"),
    mark_for_translation("GPU 推理不可用"),
    mark_for_translation("当前 GPU 推理后端不可用，请检查依赖层和显卡运行环境。"),
    mark_for_translation("识别模式不支持"),
    mark_for_translation("当前 MathCraft OCR 版本不支持该识别模式。"),
    mark_for_translation("识别进程超时"),
    mark_for_translation(
        "MathCraft OCR 运行进程响应超时，请稍后重试或检查模型运行环境。"
    ),
    mark_for_translation("模型运行异常"),
    mark_for_translation("MathCraft OCR 运行异常，请打开运行日志查看具体原因。"),
)


def external_model_test_error_user_message(error: object) -> str:
    """Translate a structured external-model connection error for the settings UI."""
    code = str(getattr(error, "user_code", "") or "").strip()
    context = getattr(error, "user_context", {})
    context = context if isinstance(context, dict) else {}

    if code == "base_url_missing":
        return tr("外部模型地址为空，请先填写 Base URL。")
    if code == "model_name_missing":
        return tr("模型名为空，请先填写本地服务中的模型名称。")
    if code == "request_timeout":
        return tr("连接测试超时，请检查服务状态或适当提高超时设置。")
    if code == "connection_unreachable":
        target = str(context.get("target") or tr("指定地址"))
        service = str(context.get("service") or "").strip()
        if service:
            return tr(
                "无法连接到 {target}，请确认 {service} 服务已启动，地址和端口填写正确。"
            ).format(target=target, service=service)
        return tr(
            "无法连接到 {target}，请确认服务已启动，地址和端口填写正确。"
        ).format(target=target)
    if code == "authentication_failed":
        return tr("接口认证失败，请检查 API Key。")
    if code == "access_denied":
        return tr("接口访问被拒绝，请检查权限或鉴权配置。")
    if code == "endpoint_not_found":
        endpoint = str(context.get("endpoint") or "/")
        return tr(
            "接口路径不存在：{endpoint}，请检查 Base URL、协议类型或接口路径配置。"
        ).format(endpoint=endpoint)
    if code == "rate_limited":
        return tr("请求过于频繁，请稍后重试。")
    if code == "server_error":
        status_code = int(context.get("status_code") or 0)
        return tr("服务端返回 {status_code}，请稍后重试或检查服务日志。").format(
            status_code=status_code
        )
    if code == "invalid_json":
        return tr("接口返回的不是有效 JSON，请检查服务协议和响应内容。")
    if code == "model_list_empty":
        return tr("接口已连接，但未能读取到可用模型列表。")
    if code == "model_not_found":
        model_name = str(context.get("model_name") or "")
        available_models = str(context.get("available_models") or "")
        return tr(
            "未找到模型 {model_name}。当前可用模型：{available_models}"
        ).format(model_name=model_name, available_models=available_models)
    if code == "image_input_unsupported":
        return tr("该接口或模型不支持图片输入，请换用支持视觉输入的模型或服务。")
    if code in {"bad_request", "http_error"}:
        status_code = int(context.get("status_code") or 0)
        detail = str(context.get("detail") or "").strip()
        if detail:
            return tr("接口返回 {status_code}。服务端信息：{detail}").format(
                status_code=status_code, detail=detail
            )
        return tr("接口返回 {status_code}，请检查服务配置。").format(
            status_code=status_code
        )
    if code == "mineru_parse_failed":
        return tr("MinerU 解析任务失败，请检查模型配置和服务日志。")
    return tr("外部模型连接测试失败，请检查服务地址、协议和网络连接。")


def translate_mathcraft_diagnostic(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for source in _MATHCRAFT_DIAGNOSTIC_TEXTS:
        if text == source:
            return tr(source)
        if text.startswith(source):
            return tr(source) + text[len(source) :]
    return text


def translate_image_input_error(value: object) -> str:
    text = str(value or "").strip()
    return tr(text) if text in _IMAGE_INPUT_ERROR_MESSAGES else text


def is_external_model_backend(backend: str | None) -> bool:
    return str(backend or "").strip().lower() in EXTERNAL_MODEL_BACKENDS


def recognition_error_code_user_message(
    code: object, backend: str | None = "mathcraft"
) -> str:
    return tr(recognition_error_code_message(code, backend))


def recognition_error_code_message(
    code: object, backend: str | None = "mathcraft"
) -> str:
    """Return the stable internal message for a structured recognition error."""
    normalized = str(code or "internal_error").strip().lower()
    if normalized == "internal_error" and is_external_model_backend(backend):
        normalized = "upstream_error"
    return _RECOGNITION_ERROR_MESSAGES.get(
        normalized, _RECOGNITION_ERROR_MESSAGES["internal_error"]
    )


def recognition_failure_user_message(
    detail: object, backend: str | None = "mathcraft"
) -> str:
    raw = str(detail or "").strip()
    classification_messages = (
        *_RECOGNITION_ERROR_MESSAGES.values(),
        CANCELED_WORKER_MESSAGE,
        EMPTY_RESULT_MESSAGE,
    )
    for source in classification_messages:
        if raw == source:
            return tr(source)
    if is_external_model_backend(backend):
        return recognition_error_code_user_message("upstream_error", backend)
    info = classify_mathcraft_failure(raw)
    return translate_mathcraft_diagnostic(info.get("user_message") or raw)


__all__ = [
    "CANCELED_WORKER_MESSAGE",
    "EMPTY_CONTENT_MESSAGE",
    "EMPTY_FORMULA_MESSAGE",
    "EMPTY_RESULT_MESSAGE",
    "EMPTY_TEXT_MESSAGE",
    "external_model_test_error_user_message",
    "is_external_model_backend",
    "recognition_error_code_message",
    "recognition_error_code_user_message",
    "recognition_failure_user_message",
    "translate_image_input_error",
    "translate_mathcraft_diagnostic",
]
