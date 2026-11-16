// User-facing text. Keys and wording come from WordAddInText and
// PowerPointAddInText; entries for OLE creation, MathType and Word format
// conversion are left out. Keys marked "Mac" have no Windows counterpart.
const SHARED = {
  zh: {
    ReadyStatus: '就绪。',
    WorkingStatus: '处理中...',
    LoadedStatus: '已加载所选公式。',
    UnchangedStatus: '公式未更改。',
    DeletedStatus: '已删除所选公式。',
    SelectedFormulaMetadataMissing: '无法找到所选公式的元数据。',
    EditorReadyStatus: '编辑器已就绪。',
    OcrRecognizingStatus: '正在识别截图公式。',
    OcrCanceledStatus: '已取消截图识别。',
    OcrLoadedStatus: '截图识别结果已加载。',
    HelpStatus: '已打开帮助。',
    SettingsStatus: '已打开设置。',
    TaskPaneShownStatus: '状态窗格已显示。',
    ConnectedAutomationStatus: '已连接到 LaTeXSnipper Automation API。',
    AutomationOcrAlreadyWaiting: '截图识别正忙，请稍后再试。',
    FormattedStatus: '已格式化 {count} 个公式。',
    FormattedWithSkippedStatus: '已格式化 {count} 个公式，跳过 {skipped} 个已不存在的公式。',
    FormattedWithFailuresStatus: '共处理 {total} 个公式：成功格式化 {succeeded} 个，失败 {failed} 个，跳过 {skipped} 个。首个错误：{reason}',
    BatchFormattingStatus: '正在格式化公式：{processed}/{total}。',
    OfficePluginLabel: 'Office 插件',
    ConnectButton: '连接',
    EditorInsert: '插入',
    ScreenshotOcrButton: '截图识别',
    CancelOcrButton: '取消识别',
    EditorSessionChanged: '公式编辑会话已变化；请重新打开编辑器后再试。',
    // Mac
    OcrEmpty: '未识别到公式内容，请在桌面端重新识别后再试。',
    OcrFailed: '截图识别未能完成，请重试。',
    OcrTimeout: '等待识别结果超时，请在桌面端发起识别后重试。',
    InvalidResponse: 'LaTeXSnipper 返回了无法识别的数据，请重启桌面端后再试。',
    DialogFailed: '无法打开窗口；请关闭已打开的 LaTeXSnipper 窗口后重试。',
    OleFormulaWindowsOnly: '所选内容是 Windows 插件创建的 OLE 公式，请在 Windows 版 LaTeXSnipper 插件中编辑。',
    OleFormulasSkipped: '已跳过 {count} 个 OLE 公式；OLE 公式请在 Windows 版插件中编辑。',
  },
  en: {
    ReadyStatus: 'Ready.',
    WorkingStatus: 'Working...',
    UnchangedStatus: 'Equation unchanged.',
    DeletedStatus: 'Deleted selected formula.',
    SelectedFormulaMetadataMissing: 'The selected formula metadata could not be found.',
    EditorReadyStatus: 'Editor ready.',
    OcrRecognizingStatus: 'Recognizing screenshot formula.',
    OcrCanceledStatus: 'Screenshot OCR canceled.',
    OcrLoadedStatus: 'Screenshot OCR result loaded.',
    HelpStatus: 'Help opened.',
    SettingsStatus: 'Settings opened.',
    TaskPaneShownStatus: 'Status pane shown.',
    ConnectedAutomationStatus: 'Connected to LaTeXSnipper Automation API.',
    AutomationOcrAlreadyWaiting: 'Screenshot OCR is busy. Wait a moment and try again.',
    FormattedStatus: 'Formatted {count} formulas.',
    FormattedWithSkippedStatus: 'Formatted {count} formulas; skipped {skipped} missing formulas.',
    FormattedWithFailuresStatus: 'Processed {total} formulas: formatted {succeeded}, failed {failed}, skipped {skipped}. First error: {reason}',
    BatchFormattingStatus: 'Formatting formulas: {processed}/{total}.',
    OfficePluginLabel: 'Office plugin',
    ConnectButton: 'Connect',
    EditorInsert: 'Insert',
    ScreenshotOcrButton: 'Screenshot OCR',
    CancelOcrButton: 'Cancel OCR',
    EditorSessionChanged: 'The formula editor session changed. Open the editor again and retry.',
    OcrEmpty: 'No formula was recognized. Recognize again in the desktop app and retry.',
    OcrFailed: 'Screenshot OCR did not complete. Please try again.',
    OcrTimeout: 'Timed out waiting for a recognition result. Start recognition in the desktop app and retry.',
    InvalidResponse: 'LaTeXSnipper returned unrecognized data. Restart the desktop app and try again.',
    DialogFailed: 'Could not open the window. Close any open LaTeXSnipper window and try again.',
    OleFormulaWindowsOnly: 'The selection is an OLE formula created by the Windows plugin. Edit it with the LaTeXSnipper plugin on Windows.',
    OleFormulasSkipped: 'Skipped {count} OLE formulas; edit OLE formulas with the Windows plugin.',
  },
};

const WORD = {
  zh: {
    SelectedFormulaRequired: '请先选择一个 LaTeXSnipper 公式。',
    InsertInsideFormulaError: '请将光标移到公式外，再插入其他公式。',
    CommandTimeoutStatus: 'Office 命令超时。若操作尚未写入 Word，文档已保持不变。',
    OmmlInsertingStatus: '正在插入 Word OMML 公式对象。',
    OmmlInsertedStatus: '已插入 OMML 公式。',
    UpdatedStatus: '已更新公式。',
    OcrWaitingStatus: '正在等待截图识别；请使用全局快捷键后框选公式区域。',
    AutoNumberedStatus: '已为所选公式添加编号。',
    RenumberedStatus: '已重排 {count} 个公式编号。',
    RenumberedWithSkippedStatus: '已重排 {count} 个公式编号，跳过 {metadataSkipped} 个缺失元数据、{numberingSkipped} 个编号字段不完整的公式。',
    NoNumberedStatus: '未找到自动编号公式。',
    AlreadyNumberedStatus: '所选公式已有编号。',
    AutoNumberDisplayOnlyStatus: '添加编号只适用于未编号的行间公式。',
    BoundaryInsertedStatus: '编号分隔符已插入。',
    ReferencePlaceholderText: '[请选择公式]',
    ReferencePlaceholderStatus: '请选择一个带编号公式以完成引用。',
    ReferenceInsertedStatus: '已插入公式引用。',
    ChapterBoundaryText: '章分隔符',
    SectionBoundaryText: '节分隔符',
    NoFormattingTargetsStatus: '未找到可格式化的公式。',
    NoFormattingNeededStatus: '所选公式已经是默认样式。',
    NoParsingTargetsStatus: '未找到可解析的公式。',
    BatchParsingStatus: '正在解析公式：{processed}/{total}。',
    ParsedStatus: '已解析 {count} 个公式。',
    ParsedWithFailuresStatus: '共处理 {total} 个公式，成功 {succeeded} 个，失败 {failed} 个。首个错误：{reason}',
    InvalidParsingSourceStatus: 'LaTeX 定界符或公式编号标记不完整。',
    ParseSourceChangedError: '源文本在解析前已发生变化。',
    EquationLabel: '公式',
    DisplayOption: '行间公式',
    AutoNumberOption: '自动编号',
    ManualNumberPlaceholder: '自定义编号',
    // Mac
    ParseObjectParagraphSkipped: '段落含有 OLE 公式，已保持不变。',
  },
  en: {
    LoadedStatus: 'Loaded selected equation.',
    SelectedFormulaRequired: 'Select a formula first.',
    InsertInsideFormulaError: 'Place the cursor outside the formula before inserting another formula.',
    CommandTimeoutStatus: 'Office command timed out. The document was left unchanged if the operation had not reached Word yet.',
    OmmlInsertingStatus: 'Inserting Word OMML formula object.',
    OmmlInsertedStatus: 'Inserted OMML equation.',
    UpdatedStatus: 'Updated equation in Word.',
    OcrWaitingStatus: 'Waiting for screenshot OCR.',
    AutoNumberedStatus: 'Added a number to the selected equation.',
    RenumberedStatus: 'Renumbered {count} equations.',
    RenumberedWithSkippedStatus: 'Renumbered {count} equations; skipped {metadataSkipped} formulas with missing metadata and {numberingSkipped} formulas with incomplete numbering fields.',
    NoNumberedStatus: 'No automatically numbered equations found.',
    AlreadyNumberedStatus: 'Selected equation already has numbering.',
    AutoNumberDisplayOnlyStatus: 'Add Number only applies to unnumbered display equations.',
    BoundaryInsertedStatus: 'Numbering separator inserted.',
    ReferencePlaceholderText: '[Select a formula]',
    ReferencePlaceholderStatus: 'Select a numbered formula to complete the reference.',
    ReferenceInsertedStatus: 'Inserted formula reference.',
    ChapterBoundaryText: 'Chapter separator',
    SectionBoundaryText: 'Section boundary',
    NoFormattingTargetsStatus: 'No formulas to format were found.',
    NoFormattingNeededStatus: 'The selected formulas already use the default style.',
    NoParsingTargetsStatus: 'No formulas to parse were found.',
    BatchParsingStatus: 'Parsing formulas: {processed}/{total}.',
    ParsedStatus: 'Parsed {count} formulas.',
    ParsedWithFailuresStatus: 'Processed {total} formulas: {succeeded} succeeded, {failed} failed. First error: {reason}',
    InvalidParsingSourceStatus: 'The LaTeX delimiter or equation tag is incomplete.',
    ParseSourceChangedError: 'The source text changed before it could be parsed.',
    EquationLabel: 'Equation',
    DisplayOption: 'Display equation',
    AutoNumberOption: 'Auto number',
    ManualNumberPlaceholder: 'Custom number',
    ParseObjectParagraphSkipped: 'A paragraph with an OLE formula was left unchanged.',
  },
};

const POWERPOINT = {
  zh: {
    SelectedFormulaRequired: '请先选择一个 LaTeXSnipper 公式。',
    CommandTimeoutStatus: 'Office 命令超时。若操作尚未写入 PowerPoint，文件保持不变。',
    ConvertingStatus: '正在转换公式。',
    InsertedImageStatus: '已插入 PNG 公式。',
    UpdatedStatus: '已更新公式。',
    DeletedManyStatus: '已删除 {count} 个所选公式。',
    ConvertedStatus: '已转换 {count} 个公式。',
    ConvertedWithSkippedStatus: '已转换 {count} 个公式，跳过 {skipped} 个已不存在的公式。',
    ConvertedWithFailuresStatus: '共处理 {total} 个公式：成功转换 {succeeded} 个，失败 {failed} 个，跳过 {skipped} 个。首个错误：{reason}',
    NoConversionNeededStatus: '所选公式已经是目标格式。',
    NoFormattingNeededStatus: '没有需要格式化的公式。',
    BatchConvertingStatus: '正在转换公式：{processed}/{total}。',
    OcrWaitingStatus: '正在等待截图识别。',
    EquationLabel: '公式',
    NoActiveSlide: '请先打开一个 PowerPoint 幻灯片，再插入公式。',
    // Mac
    InsertedSvgStatus: '已插入 SVG 公式。',
  },
  en: {
    LoadedStatus: 'Loaded selected formula.',
    UnchangedStatus: 'Formula unchanged.',
    SelectedFormulaRequired: 'Select a LaTeXSnipper formula first.',
    CommandTimeoutStatus: 'Office command timed out. The file was left unchanged if the operation had not reached PowerPoint yet.',
    ConvertingStatus: 'Converting formula.',
    InsertedImageStatus: 'Inserted PNG formula.',
    UpdatedStatus: 'Updated formula.',
    DeletedManyStatus: 'Deleted {count} selected formulas.',
    ConvertedStatus: 'Converted {count} formulas.',
    ConvertedWithSkippedStatus: 'Converted {count} formulas; skipped {skipped} missing formulas.',
    ConvertedWithFailuresStatus: 'Processed {total} formulas: converted {succeeded}, failed {failed}, skipped {skipped}. First error: {reason}',
    NoConversionNeededStatus: 'The selected formulas already use the target format.',
    NoFormattingNeededStatus: 'No formulas need formatting.',
    BatchConvertingStatus: 'Converting formulas: {processed}/{total}.',
    OcrWaitingStatus: 'Waiting for screenshot OCR.',
    EquationLabel: 'Formula',
    NoActiveSlide: 'Open a PowerPoint slide before inserting a formula.',
    InsertedSvgStatus: 'Inserted SVG formula.',
  },
};

export function isChinese(locale) {
  return String(locale || '').toLowerCase().startsWith('zh');
}

/** Text for `key` with {placeholders} replaced; an unknown key returns the key, as on Windows. */
export function text(locale, host, key, values = {}) {
  const language = isChinese(locale) ? 'zh' : 'en';
  const hostTable = host === 'word' ? WORD : POWERPOINT;
  const template = hostTable[language][key] ?? SHARED[language][key] ?? hostTable.zh[key] ?? SHARED.zh[key] ?? key;
  return Object.entries(values).reduce((result, [name, value]) => result.replaceAll(`{${name}}`, String(value)), template);
}

/**
 * OfficeOperationError.Describe: messages without Chinese text get the
 * Chinese "operation failed" prefix, timeouts the "timed out" prefix.
 */
export function describeError(error) {
  // Office.js reports bare codes such as GeneralException; where it failed is the useful part.
  const location = error?.debugInfo?.errorLocation;
  const message = String(error?.message || error?.name || error || '').trim() || 'Error';
  const detail = location && !message.includes(location) ? `${message}（${location}）` : message;
  if (error?.name === 'TimeoutError') return '操作超时：' + detail;
  return /[㐀-鿿]/u.test(detail) ? detail : '操作失败：' + detail;
}
