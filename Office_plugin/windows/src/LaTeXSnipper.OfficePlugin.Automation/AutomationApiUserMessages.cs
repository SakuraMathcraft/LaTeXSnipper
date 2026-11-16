namespace LaTeXSnipper.OfficePlugin.Automation;

/// <summary>Chinese user-facing messages for Automation API failures.</summary>
public static class AutomationApiUserMessages
{
    public const string DesktopUnavailable = "无法连接到 LaTeXSnipper。请先启动桌面端，在“设置”中开启“自动化接口”，然后重试。";
    public const string ConnectionInfoInvalid = "LaTeXSnipper 连接信息无效。请在桌面端关闭并重新开启“自动化接口”，然后重试。";
    public const string RequestTimeout = "LaTeXSnipper 响应超时，请确认桌面端仍在运行，然后重试。";
    public const string ScreenshotTimeout = "等待识别结果超时，请在桌面端发起识别后重试。";
    public const string RecognitionFailed = "截图识别未能完成，请重试。";
    public const string InvalidResponse = "LaTeXSnipper 返回了无法识别的数据，请重启桌面端后再试。";

    public static string ForErrorCode(string code)
    {
        return (code ?? string.Empty).Trim() switch
        {
            "unauthorized" => "连接凭据已失效，请在桌面端重新开启“自动化接口”后再试。",
            "forbidden" => "当前连接没有执行此操作的权限。",
            "queue_full" => "识别任务较多，请稍后再试。",
            "next_result_busy" => "已有客户端正在等待下一次识别结果，请稍后再试。",
            "recognition_failed" => RecognitionFailed,
            "model_unavailable" => "MathCraft 模型当前不可用，请检查桌面端模型状态。",
            "backend_unavailable" => "外部模型尚未配置或当前不可用。",
            "backend_unsupported" => "当前外部模型不支持此类识别。",
            "mode_unsupported" => "当前识别引擎不支持所选识别模式。",
            "upstream_timeout" => "外部模型响应超时，请稍后再试。",
            "upstream_error" => "外部模型调用失败，请检查桌面端的外部模型配置。",
            "timeout" => ScreenshotTimeout,
            "canceled" => "截图识别已取消。",
            "empty_formula" => "未识别到公式内容，请在桌面端重新识别后再试。",
            "empty_text" => "未识别到文本内容，请在桌面端重新识别后再试。",
            "empty_content" => "未检测到可识别内容，请在桌面端重新识别后再试。",
            "rate_limited" => "请求过于频繁，请稍后再试。",
            "job_not_found" or "job_expired" => "识别任务已失效，请重新等待下一次识别结果。",
            "invalid_request" or "invalid_backend" or "invalid_mode" => "识别请求无效，请重试。",
            _ => RecognitionFailed,
        };
    }
}
