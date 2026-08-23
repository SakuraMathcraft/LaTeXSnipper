using System;
using System.Globalization;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public static class PowerPointAddInText
{
    public static string GetExceptionMessage(Exception exception)
    {
        string message = exception?.Message?.Trim() ?? string.Empty;
        foreach (char value in message)
        {
            if (value >= '\u3400' && value <= '\u9fff')
            {
                return message;
            }
        }

        return exception is TimeoutException
            ? "操作超时，请稍后重试。"
            : "操作失败，请重试；若问题持续，请重新启动 Office 和 LaTeXSnipper。";
    }

    public static string Get(string key)
    {
        return CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "zh"
            ? GetChinese(key)
            : GetEnglish(key);
    }

    private static string GetEnglish(string key)
    {
        return key switch
        {
            "RibbonTab" => "LaTeXSnipper",
            "FormulaGroup" => "Formula",
            "EditGroup" => "Edit",
            "ConversionGroup" => "Conversion",
            "FormattingGroup" => "Formula Style",
            "ToolsGroup" => "Tools",
            "InsertFormulaButton" => "Insert Formula",
            "ScreenshotOcrButton" => "Screenshot OCR",
            "CancelOcrButton" => "Cancel OCR",
            "LoadSelectedButton" => "Load Selected",
            "DeleteSelectedButton" => "Delete Selected",
            "ToOleButton" => "To OLE",
            "ToPngButton" => "To PNG",
            "FormatSelectedButton" => "Format Selected",
            "FormatAllButton" => "Format All",
            "ShowTaskPaneButton" => "Status Pane",
            "SettingsButton" => "Settings",
            "HelpButton" => "Help",
            "InsertFormulaTip" => "Open the formula editor.",
            "ScreenshotOcrTip" => "Wait for the next LaTeXSnipper recognition result; click again to cancel.",
            "LoadSelectedTip" => "Load the selected formula into the editor.",
            "DeleteSelectedTip" => "Delete the selected managed formulas.",
            "ToOleTip" => "Convert the selected PNG formulas to OLE.",
            "ToPngTip" => "Convert the selected OLE formulas to PNG.",
            "FormatSelectedTip" => "Reset selected formulas to the default font, color, and natural size.",
            "FormatAllTip" => "Restore formulas with modified dimensions to their natural size.",
            "ShowTaskPaneTip" => "Show the status pane.",
            "SettingsTip" => "Open LaTeXSnipper settings.",
            "HelpTip" => "Show Office plugin help.",
            "OfficePluginLabel" => "Office plugin",
            "EquationLabel" => "Formula",
            "ConnectButton" => "Connect",
            "EditorInsert" => "Insert",
            "Cancel" => "Cancel",
            "ErrorTitle" => "LaTeXSnipper",
            "SelectedFormulaRequired" => "Select a LaTeXSnipper formula first.",
            "SelectedFormulaMetadataMissing" => "The selected formula metadata could not be found.",
            "TaskPaneTitle" => "LaTeXSnipper",
            "ReadyStatus" => "Ready.",
            "WorkingStatus" => "Working...",
            "EditorReadyStatus" => "Editor ready.",
            "ConvertingStatus" => "Converting formula.",
            "OleInsertingStatus" => "Inserting LaTeXSnipper OLE formula object.",
            "CommandTimeoutStatus" => "Office command timed out. The file was left unchanged if the operation had not reached PowerPoint yet.",
            "InsertedFormulaStatus" => "Inserted OLE formula.",
            "InsertedImageStatus" => "Inserted PNG formula.",
            "UpdatedStatus" => "Updated formula.",
            "UnchangedStatus" => "Formula unchanged.",
            "LoadedStatus" => "Loaded selected formula.",
            "DeletedStatus" => "Deleted selected formula.",
            "DeletedManyStatus" => "Deleted {count} selected formulas.",
            "ConvertedStatus" => "Converted {count} formulas.",
            "ConvertedWithSkippedStatus" => "Converted {count} formulas; skipped {skipped} missing formulas.",
            "NoConversionNeededStatus" => "The selected formulas already use the target format.",
            "FormattedStatus" => "Formatted {count} formulas.",
            "FormattedWithSkippedStatus" => "Formatted {count} formulas; skipped {skipped} missing formulas.",
            "NoFormattingNeededStatus" => "No formulas need formatting.",
            "BatchConvertingStatus" => "Converting formulas: {processed}/{total}.",
            "BatchFormattingStatus" => "Formatting formulas: {processed}/{total}.",
            "OcrWaitingStatus" => "Waiting for screenshot OCR.",
            "OcrRecognizingStatus" => "Recognizing screenshot formula.",
            "OcrCanceledStatus" => "Screenshot OCR canceled.",
            "OcrLoadedStatus" => "Screenshot OCR result loaded.",
            "HelpStatus" => "Help opened.",
            "SettingsStatus" => "Settings opened.",
            "SettingsTitle" => "LaTeXSnipper PowerPoint Plugin Settings",
            "TaskPaneShownStatus" => "Status pane shown.",
            "ConnectedAutomationStatus" => "Connected to LaTeXSnipper Automation API.",
            "AutomationOcrAlreadyWaiting" => "Screenshot OCR is busy. Wait a moment and try again.",
            _ => key,
        };
    }

    private static string GetChinese(string key)
    {
        return key switch
        {
            "RibbonTab" => "LaTeXSnipper",
            "FormulaGroup" => "公式",
            "EditGroup" => "编辑",
            "ConversionGroup" => "转换",
            "FormattingGroup" => "公式样式",
            "ToolsGroup" => "工具",
            "InsertFormulaButton" => "插入公式",
            "ScreenshotOcrButton" => "截图识别",
            "CancelOcrButton" => "取消识别",
            "LoadSelectedButton" => "加载所选",
            "DeleteSelectedButton" => "删除所选",
            "ToOleButton" => "转为 OLE",
            "ToPngButton" => "转为 PNG",
            "FormatSelectedButton" => "格式化所选",
            "FormatAllButton" => "格式化全文",
            "ShowTaskPaneButton" => "状态窗格",
            "SettingsButton" => "设置",
            "HelpButton" => "帮助",
            "InsertFormulaTip" => "打开公式编辑器。",
            "ScreenshotOcrTip" => "等待 LaTeXSnipper 的下一次识别结果；再次单击可取消。",
            "LoadSelectedTip" => "将所选公式加载到编辑器中。",
            "DeleteSelectedTip" => "删除所选受管理公式。",
            "ToOleTip" => "将所选 PNG 公式转换为 OLE。",
            "ToPngTip" => "将所选 OLE 公式转换为 PNG。",
            "FormatSelectedTip" => "将所选公式恢复为默认字体、颜色和自然大小。",
            "FormatAllTip" => "仅将尺寸被修改的公式恢复为自然大小。",
            "ShowTaskPaneTip" => "显示状态窗格。",
            "SettingsTip" => "打开 LaTeXSnipper 设置。",
            "HelpTip" => "显示 Office 插件帮助。",
            "OfficePluginLabel" => "Office 插件",
            "EquationLabel" => "公式",
            "ConnectButton" => "连接",
            "EditorInsert" => "插入",
            "Cancel" => "取消",
            "ErrorTitle" => "LaTeXSnipper",
            "SelectedFormulaRequired" => "请先选择一个 LaTeXSnipper 公式。",
            "SelectedFormulaMetadataMissing" => "无法找到所选公式的元数据。",
            "TaskPaneTitle" => "LaTeXSnipper",
            "ReadyStatus" => "就绪。",
            "WorkingStatus" => "处理中...",
            "EditorReadyStatus" => "编辑器已就绪。",
            "ConvertingStatus" => "正在转换公式。",
            "OleInsertingStatus" => "正在插入 LaTeXSnipper OLE 公式对象。",
            "CommandTimeoutStatus" => "Office 命令超时。若操作尚未写入 PowerPoint，文件保持不变。",
            "InsertedFormulaStatus" => "已插入 OLE 公式。",
            "InsertedImageStatus" => "已插入 PNG 公式。",
            "UpdatedStatus" => "已更新公式。",
            "UnchangedStatus" => "公式未更改。",
            "LoadedStatus" => "已加载所选公式。",
            "DeletedStatus" => "已删除所选公式。",
            "DeletedManyStatus" => "已删除 {count} 个所选公式。",
            "ConvertedStatus" => "已转换 {count} 个公式。",
            "ConvertedWithSkippedStatus" => "已转换 {count} 个公式，跳过 {skipped} 个已不存在的公式。",
            "NoConversionNeededStatus" => "所选公式已经是目标格式。",
            "FormattedStatus" => "已格式化 {count} 个公式。",
            "FormattedWithSkippedStatus" => "已格式化 {count} 个公式，跳过 {skipped} 个已不存在的公式。",
            "NoFormattingNeededStatus" => "没有需要格式化的公式。",
            "BatchConvertingStatus" => "正在转换公式：{processed}/{total}。",
            "BatchFormattingStatus" => "正在格式化公式：{processed}/{total}。",
            "OcrWaitingStatus" => "正在等待截图识别。",
            "OcrRecognizingStatus" => "正在识别截图公式。",
            "OcrCanceledStatus" => "已取消截图识别。",
            "OcrLoadedStatus" => "截图识别结果已加载。",
            "HelpStatus" => "已打开帮助。",
            "SettingsStatus" => "已打开设置。",
            "SettingsTitle" => "LaTeXSnipper PowerPoint 插件设置",
            "TaskPaneShownStatus" => "状态窗格已显示。",
            "ConnectedAutomationStatus" => "已连接到 LaTeXSnipper Automation API。",
            "AutomationOcrAlreadyWaiting" => "截图识别正忙，请稍后再试。",
            _ => key,
        };
    }
}
