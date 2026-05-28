type Locale = "en-US" | "zh-CN";
type Values = Record<string, string | number>;

const TEXT = {
  "en-US": {
    officeAddin: "{host} add-in",
    checkConnection: "Check connection",
    connect: "Connect",
    workingButton: "Working...",
    waitingOffice: "Waiting for Office.",
    ready: "Ready.",
    equation: "Equation",
    keyboard: "Keyboard",
    display: "Display",
    autoNumber: "Auto number",
    manualNumber: "Manual #",
    screenshotOcr: "Screenshot OCR",
    insert: "Insert",
    update: "Update",
    numbering: "Numbering",
    renumberAll: "Renumber all",
    advanced: "Advanced",
    bridgeUrl: "Bridge URL",
    bridgeToken: "Bridge token",
    symbols: "Symbols",
    latexSource: "LaTeX Source",
    toggleSymbols: "Toggle symbol panel",
    greekLower: "Greek (lower)",
    greekUpper: "Greek (upper)",
    operators: "Operators",
    bigOperators: "Big Operators",
    relations: "Relations",
    setsLogic: "Sets & Logic",
    numberSets: "Number Sets",
    arrows: "Arrows",
    delimiters: "Delimiters",
    functions: "Functions",
    accents: "Accents & Decorations",
    fontStyles: "Font Styles",
    misc: "Misc",
    structures: "Structures",
    selectedEquation: "LaTeXSnipper equation selected. Click Load to edit.",
    connectedBridge: "Connected to LaTeXSnipper.",
    startBridge: "Enable the Office add-in feature in LaTeXSnipper desktop settings to connect.",
    converting: "Converting LaTeX through bridge.",
    converted: "Converted to OMML.",
    insertedPpt: "Inserted formula image into PowerPoint.",
    insertedWord: "Inserted equation into Word.",
    wordOnlyEdit: "Equation editing is available in Word only.",
    openedEditor: "Opened equation in editor.",
    wordOnlyDelete: "Deleting equations is available in Word only.",
    deletedEquation: "Deleted selected equation.",
    wordOnlyNumbering: "Equation numbering is available in Word only.",
    selectNumber: "Select a LaTeXSnipper equation to add numbering.",
    missingSource: "The selected equation does not have saved LaTeX source.",
    alreadyNumbered: "Selected equation already has numbering.",
    addedNumber: "Added numbering to selected equation.",
    renumbered: "Renumbered {count} equations.",
    noNumbered: "No numbered LaTeXSnipper equations found.",
    waitingCapture: "Waiting for the next LaTeXSnipper recognition. Use the global shortcut, then capture a region.",
    recognizing: "Recognizing formula in LaTeXSnipper. First OCR after startup can take longer.",
    ocrLoaded: "Screenshot OCR result loaded into the editor.",
    ocrEmpty: "Screenshot OCR returned an empty result.",
    pptManualNumberPrompt: "Enter a number in the editor, then insert the numbered formula image.",
    connectRefresh: "Click Connect to refresh the LaTeXSnipper bridge token.",
    latexRequired: "LaTeX is required.",
    failedEditor: "Failed to open editor: {message}",
    failedHelp: "Failed to open help: {message}",
    updatedWord: "Updated equation in Word.",
    editingEquation: "Editing equation - click Update to apply changes.",
    inserting: "Inserting...",
    discardFormula: "Discard unsaved formula?",
    rows: "Rows",
    columns: "Columns",
    fraction: "Fraction",
    superscript: "Superscript",
    subscript: "Subscript",
    squareRoot: "Square root",
    subSup: "Sub + Sup",
    sum: "Sum",
    integral: "Integral",
    limit: "Limit",
    determinant: "Determinant",
    cases: "Cases",
    aligned: "Aligned",
    binomial: "Binomial",
    nthRoot: "Nth root",
    product: "Product",
    gather: "Gather"
  },
  "zh-CN": {
    officeAddin: "{host} 加载项",
    checkConnection: "检查连接",
    connect: "连接",
    workingButton: "处理中...",
    waitingOffice: "正在等待 Office。",
    ready: "就绪。",
    equation: "公式",
    keyboard: "键盘",
    display: "显示公式",
    autoNumber: "自动编号",
    manualNumber: "自定义编号",
    screenshotOcr: "截图识别",
    insert: "插入",
    update: "更新",
    numbering: "编号",
    renumberAll: "重新编号全部",
    advanced: "高级设置",
    bridgeUrl: "Bridge 地址",
    bridgeToken: "Bridge 令牌",
    symbols: "符号",
    latexSource: "LaTeX 源码",
    toggleSymbols: "显示或隐藏符号面板",
    greekLower: "小写希腊字母",
    greekUpper: "大写希腊字母",
    operators: "运算符",
    bigOperators: "大型运算符",
    relations: "关系符",
    setsLogic: "集合与逻辑",
    numberSets: "数集",
    arrows: "箭头",
    delimiters: "定界符",
    functions: "函数",
    accents: "重音与修饰",
    fontStyles: "字体样式",
    misc: "其他符号",
    structures: "结构",
    selectedEquation: "已选中 LaTeXSnipper 公式。点击“加载选中项”进行编辑。",
    connectedBridge: "已连接 LaTeXSnipper。",
    startBridge: "请在 LaTeXSnipper 桌面端设置中启用 Office 加载项功能以连接。",
    converting: "正在通过 Bridge 转换 LaTeX。",
    converted: "已转换为 OMML。",
    insertedPpt: "已将公式图像插入 PowerPoint。",
    insertedWord: "已将公式插入 Word。",
    wordOnlyEdit: "公式加载编辑仅适用于 Word。",
    openedEditor: "已在编辑器中打开公式。",
    wordOnlyDelete: "删除公式仅适用于 Word。",
    deletedEquation: "已删除选中的公式。",
    wordOnlyNumbering: "已有公式的编号转换仅适用于 Word。",
    selectNumber: "请选择一个 LaTeXSnipper 公式以添加编号。",
    missingSource: "选中公式没有保存的 LaTeX 源码。",
    alreadyNumbered: "选中公式已经带有编号。",
    addedNumber: "已为选中公式添加编号。",
    renumbered: "已重新编号 {count} 个公式。",
    noNumbered: "未找到自动编号的 LaTeXSnipper 公式。",
    waitingCapture: "正在等待下一次 LaTeXSnipper 截图识别；请使用全局快捷键后框选区域。",
    recognizing: "LaTeXSnipper 正在识别公式；首次识别可能需要更长时间。",
    ocrLoaded: "截图识别结果已载入编辑器。",
    ocrEmpty: "截图识别返回了空结果。",
    pptManualNumberPrompt: "请在编辑器中填写编号，再插入带编号的公式图像。",
    connectRefresh: "请点击“连接”刷新 LaTeXSnipper Bridge 令牌。",
    latexRequired: "必须填写 LaTeX。",
    failedEditor: "无法打开编辑器：{message}",
    failedHelp: "无法打开帮助：{message}",
    updatedWord: "已更新 Word 公式。",
    editingEquation: "正在编辑公式，点击“更新”应用更改。",
    inserting: "正在插入...",
    discardFormula: "放弃尚未保存的公式吗？",
    rows: "行数",
    columns: "列数",
    fraction: "分式",
    superscript: "上标",
    subscript: "下标",
    squareRoot: "平方根",
    subSup: "上下标",
    sum: "求和",
    integral: "积分",
    limit: "极限",
    determinant: "行列式",
    cases: "分段",
    aligned: "对齐",
    binomial: "二项式",
    nthRoot: "n 次根",
    product: "乘积",
    gather: "多行"
  }
} as const;

let activeLocale: Locale = "en-US";

export function configureLocale(displayLanguage?: string): void {
  const candidate = displayLanguage || navigator.language || "en-US";
  activeLocale = candidate.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US";
  document.documentElement.lang = activeLocale;
}

export function currentLocale(): Locale {
  return activeLocale;
}

export function t(key: keyof typeof TEXT["en-US"], values: Values = {}): string {
  let value: string = TEXT[activeLocale][key] || TEXT["en-US"][key];
  for (const [name, replacement] of Object.entries(values)) {
    value = value.replaceAll(`{${name}}`, String(replacement));
  }
  return value;
}

export function localizeDocument(root: ParentNode = document): void {
  root.querySelectorAll<HTMLElement>("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n as keyof typeof TEXT["en-US"]);
  });
  root.querySelectorAll<HTMLElement>("[data-i18n-title]").forEach((element) => {
    element.title = t(element.dataset.i18nTitle as keyof typeof TEXT["en-US"]);
  });
  root.querySelectorAll<HTMLInputElement>("[data-i18n-placeholder]").forEach((element) => {
    element.placeholder = t(element.dataset.i18nPlaceholder as keyof typeof TEXT["en-US"]);
  });
}

const ERROR_TRANSLATIONS: Record<string, string> = {
  "The bridge did not return editable OMML.": "Bridge 未返回可编辑的 OMML。",
  "Word API 1.3 is required for editable equations.": "编辑公式需要 Word API 1.3。",
  "Equation ID is required for update.": "更新公式需要公式 ID。",
  "Select a LaTeXSnipper equation to delete.": "请选择要删除的 LaTeXSnipper 公式。",
  "Deleting equations is available in Word only.": "删除公式仅适用于 Word。",
  "The selected equation could not be found in this document.": "在当前文档中找不到选中的公式。",
  "Select a LaTeXSnipper equation first.": "请先选择一个 LaTeXSnipper 公式。",
  "The selected equation does not have saved LaTeX source.": "选中公式没有保存的 LaTeX 源码。",
  "Word API 1.3 is required for equation selection.": "选择公式需要 Word API 1.3。",
  "Renumbering is available in Word only.": "重新编号仅适用于 Word。",
  "Place the cursor outside the LaTeXSnipper equation before inserting another formula.": "请将光标移到 LaTeXSnipper 公式外，再插入其他公式。",
  "Place the cursor outside the numbered LaTeXSnipper equation before inserting another formula.": "请将光标移到带编号的 LaTeXSnipper 公式外，再插入其他公式。",
  "The equation could not be found in this document.": "在当前文档中找不到该公式。",
  "The numbered equation label could not be found in this document.": "在当前文档中找不到该公式的编号。",
  "This numbered equation shares a table with another formula. Delete or separate it before changing its numbering mode.": "该编号公式与另一公式共享表格；请先删除或分开它，再更改编号模式。",
  "The bridge did not return a PowerPoint image.": "Bridge 未返回 PowerPoint 公式图像。",
  "Failed to compose PowerPoint numbering.": "无法生成带编号的 PowerPoint 公式图像。",
  "Failed to trim PowerPoint formula image.": "无法裁剪 PowerPoint 公式图像。",
  "PowerPoint numbered images require a manual number.": "PowerPoint 带编号公式图像必须填写自定义编号。",
  "Failed to insert image into PowerPoint.": "无法将公式图像插入 PowerPoint。",
  "Bridge config did not return a session token.": "Bridge 配置未返回会话令牌。",
  "Failed to save Office document settings.": "无法保存 Office 文档设置。",
  "Bridge token is required.": "需要 Bridge 令牌。",
  "Bridge request timed out.": "Bridge 请求超时。",
  "MathLive editor failed to load.": "公式编辑器加载失败，请重新打开加载项。"
};

export function displayMessage(message: string): string {
  if (activeLocale !== "zh-CN") {
    return message;
  }
  if (message.startsWith("Bridge is not reachable at ")) {
    return `无法连接到 ${message.replace("Bridge is not reachable at ", "Bridge：")}`;
  }
  if (message.startsWith("Bridge request failed: ")) {
    return message.replace("Bridge request failed: ", "Bridge 请求失败：");
  }
  return ERROR_TRANSLATIONS[message] || message;
}
