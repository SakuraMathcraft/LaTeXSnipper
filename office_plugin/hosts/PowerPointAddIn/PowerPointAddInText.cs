using System.Globalization;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public static class PowerPointAddInText
{
    public static string Get(string key)
    {
        bool zh = CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "zh";
        return zh ? GetChinese(key) : GetEnglish(key);
    }

    private static string GetEnglish(string key)
    {
        return key switch
        {
            "RibbonTab" => "LaTeXSnipper",
            "FormulaGroup" => "Formula",
            "EditGroup" => "Edit",
            "ToolsGroup" => "Tools",
            "InsertFormulaButton" => "Insert Formula",
            "ScreenshotOcrButton" => "Screenshot OCR",
            "CancelOcrButton" => "Cancel OCR",
            "LoadSelectedButton" => "Load Selected",
            "DeleteSelectedButton" => "Delete Selected",
            "ShowTaskPaneButton" => "Status Pane",
            "SettingsButton" => "Settings",
            "HelpButton" => "Help",
            "InsertFormulaTip" => "Insert the current LaTeX as a formula image.",
            "ScreenshotOcrTip" => "Wait for the next capture; click again to cancel.",
            "LoadSelectedTip" => "Load the selected formula into the editor.",
            "DeleteSelectedTip" => "Delete the selected formula and its metadata.",
            "ShowTaskPaneTip" => "Show the status pane.",
            "SettingsTip" => "Configure plugin settings.",
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
            "InsertedStatus" => "Inserted formula image.",
            "LoadedStatus" => "Loaded selected formula.",
            "DeletedStatus" => "Deleted selected formula.",
            "DeletedManyStatus" => "Deleted {count} selected formulas.",
            "OcrWaitingStatus" => "Waiting for screenshot OCR.",
            "OcrRecognizingStatus" => "Recognizing screenshot formula.",
            "OcrCanceledStatus" => "Screenshot OCR canceled.",
            "OcrLoadedStatus" => "Screenshot OCR result loaded.",
            "HelpStatus" => "Help opened.",
            "SettingsStatus" => "Settings opened.",
            "SettingsTitle" => "LaTeXSnipper PowerPoint Plugin Settings",
            "TaskPaneShownStatus" => "Status pane shown.",
            "ConnectedBridgeStatus" => "Connected to LaTeXSnipper.",
            "BridgeOcrAlreadyWaiting" => "Screenshot OCR is busy. Wait a moment and try again.",
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
            "ToolsGroup" => "工具",
            "InsertFormulaButton" => "插入公式",
            "ScreenshotOcrButton" => "截图识别",
            "CancelOcrButton" => "取消识别",
            "LoadSelectedButton" => "加载所选",
            "DeleteSelectedButton" => "删除所选",
            "ShowTaskPaneButton" => "状态窗格",
            "SettingsButton" => "设置",
            "HelpButton" => "帮助",
            "InsertFormulaTip" => "将当前 LaTeX 公式作为图片插入幻灯片。",
            "ScreenshotOcrTip" => "等待下一次截图；再次点击可取消。",
            "LoadSelectedTip" => "将所选公式加载到编辑器中。",
            "DeleteSelectedTip" => "删除所选公式及其元数据。",
            "ShowTaskPaneTip" => "显示状态窗格。",
            "SettingsTip" => "配置插件设置。",
            "HelpTip" => "显示插件帮助。",
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
            "CommandTimeoutStatus" => "Office 命令超时。若操作尚未写入 PowerPoint，文件已保持不变。",
            "InsertedStatus" => "已插入公式图片。",
            "LoadedStatus" => "已加载所选公式。",
            "DeletedStatus" => "已删除所选公式。",
            "DeletedManyStatus" => "已删除 {count} 个所选公式。",
            "OcrWaitingStatus" => "正在等待截图识别；请使用全局快捷键后框选公式区域。",
            "OcrRecognizingStatus" => "正在识别截图公式。",
            "OcrCanceledStatus" => "已取消截图识别。",
            "OcrLoadedStatus" => "截图识别结果已加载。",
            "HelpStatus" => "已打开帮助。",
            "SettingsStatus" => "已打开设置。",
            "SettingsTitle" => "LaTeXSnipper PowerPoint 插件设置",
            "TaskPaneShownStatus" => "状态窗格已显示。",
            "ConnectedBridgeStatus" => "已连接到 LaTeXSnipper。",
            "BridgeOcrAlreadyWaiting" => "截图识别正忙，请稍后再试。",
            _ => key,
        };
    }
}
