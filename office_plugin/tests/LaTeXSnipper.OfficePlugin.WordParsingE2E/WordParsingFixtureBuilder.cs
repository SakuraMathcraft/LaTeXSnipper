using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal static class WordParsingFixtureBuilder
{
    private const int WdContentControlRichText = 0;
    private const int WdFieldEmpty = -1;
    private const int WdLineSpaceMultiple = 5;
    private const int WdPreferredWidthPoints = 3;

    public const int ExpectedCandidateCount = 37;
    public const int ExpectedManagedFormulaCount = 33;
    public const int ExpectedFailedCandidateCount = 4;

    public static void Build(dynamic document, FormulaInsertionBackend backend)
    {
        ConfigureDocument(document);
        AppendParagraph(document, @"$E_{\mathrm{start}}=0$ 文档首字符处的完整公式。");
        AppendTitle(document, "欧拉—拉格朗日方程：公式解析自动化端到端测试");
        AppendParagraph(
            document,
            "测试后端：" + (backend == FormulaInsertionBackend.Ole ? "OLE" : "Word OMML")
            + "。本文由自动化测试生成，覆盖正文、相邻公式、复杂公式、失败隔离、真实表格和不安全区域。");

        AppendHeading(document, "1. 正文与相邻公式");
        AppendParagraph(
            document,
            @"基本行内公式：轨迹 $q(t)$，广义动量 \(p_i=\frac{\partial L}{\partial\dot q_i}\)。");
        AppendParagraph(document, @"相邻公式：$q$$\dot q$$\ddot q$。");
        AppendParagraph(document, @"转义美元：价格 \$100 不解析；偶数反斜杠 \\$x$ 只解析 x。");
        AppendParagraph(document, @"公式内部转义美元：$C(q)=\$100+q$。");

        AppendHeading(document, "2. 定界符词法边界");
        AppendParagraph(document, @"圆括号定界符：偶数前导反斜杠 \\(a+b\) 不解析；奇数前导反斜杠 \\\(a-b\) 解析。");
        AppendParagraph(document, @"方括号定界符：偶数前导反斜杠 \\[a+b\] 不解析；奇数前导反斜杠 \\\[a-b\] 解析。");
        AppendParagraph(document, @"混合内容一：\(a+\text{\$100}\)。");
        AppendParagraph(document, @"混合内容二：\[E=\text{price \$100}\]");
        AppendParagraph(document, @"混合内容三：$a+\text{\(literal\)}$。");
        AppendParagraph(document, @"孤立结束符号 $、\) 和 \] 均不得形成候选。");

        AppendHeading(document, "3. 行间公式与 tag");
        AppendParagraph(
            document,
            @"前文 $$\frac{\mathrm d}{\mathrm dt}\left(\frac{\partial L}{\partial\dot q}\right)-\frac{\partial L}{\partial q}=0$$ 后文。");
        AppendParagraph(
            document,
            @"$$\frac{\partial F}{\partial y}=0\tag{5}$$");
        AppendParagraph(document, @"$$E=mc^2\tag {  7  }$$");
        AppendParagraph(document, @"$$\tag{8}E=mc^2$$");
        AppendParagraph(
            document,
            "$$E=mc^2 % \\tag{ignored}\r+0$$");
        AppendParagraph(
            document,
            @"\[\frac{\partial\mathcal L}{\partial\phi}-\partial_\mu\left(\frac{\partial\mathcal L}{\partial(\partial_\mu\phi)}\right)=0\tag{EL-field}\]");
        AppendParagraph(
            document,
            "\\[\\begin{aligned}\r"
            + "S[q+\\varepsilon\\eta]&=\\int_{t_0}^{t_1}L(q+\\varepsilon\\eta,\\dot q+\\varepsilon\\dot\\eta,t)\\,\\mathrm dt,\\\\\r"
            + "\\delta S&=\\int_{t_0}^{t_1}\\left[\\frac{\\partial L}{\\partial q}-\\frac{\\mathrm d}{\\mathrm dt}\\left(\\frac{\\partial L}{\\partial\\dot q}\\right)\\right]\\eta\\,\\mathrm dt.\r"
            + "\\end{aligned}\\]");
        AppendParagraph(
            document,
            @"$$\frac{\mathrm d}{\mathrm dt}\left(\frac{\partial L}{\partial\dot q}\right)-\frac{\partial L}{\partial q}=0\label{eq:el}$$");
        AppendParagraph(document, @"正文中的 \ref{eq:el} 与 \eqref{eq:el} 不映射为插件引用。");

        AppendHeading(document, "4. 空公式、未闭合公式与失败隔离");
        AppendParagraph(document, @"空公式保持原文：$   $、\(   \)、$$$$、\[   \]。");
        AppendParagraph(document, @"未闭合美元公式：$\frac{\partial L}{\partial q}");
        AppendParagraph(document, @"后续正常公式：$E=T+V$。");
        AppendParagraph(document, @"未闭合圆括号公式：\(\frac{\partial L}{\partial\dot q}");
        AppendParagraph(document, @"后续正常公式：\(p_i=\frac{\partial L}{\partial\dot q_i}\)。");
        AppendParagraph(document, @"未闭合行间公式：$$a+b");
        AppendParagraph(document, @"后续正常行内公式：$x$。");
        AppendParagraph(document, @"后续正常行间公式：$$c=d$$");
        AppendParagraph(document, @"空 tag：$$E=T+V\tag{}$$");
        AppendParagraph(document, @"重复 tag：$$m\ddot q+kq=0\tag{A}\tag{B}$$");
        AppendParagraph(document, @"未闭合 tag：$$\ddot q+\omega^2q=0\tag{osc$$");
        AppendParagraph(document, @"tag 星号：$$\frac{\partial L}{\partial q}=0\tag*{star}$$");

        AppendHeading(document, "5. 真实 Word 表格");
        AppendTable(document);

        AppendHeading(document, "6. 不安全区域");
        dynamic protectedRange = AppendParagraph(document, @"受控区域 $unsafe$");
        dynamic control = document.ContentControls.Add(WdContentControlRichText, protectedRange);
        control.Tag = "formula-parsing-e2e-unsafe";

        dynamic fieldRange = EndRange(document);
        document.Fields.Add(fieldRange, WdFieldEmpty, "QUOTE \"$field$\"", true);
        AppendParagraph(document, string.Empty);

        dynamic hyperlinkRange = AppendParagraph(document, @"$link$");
        document.Hyperlinks.Add(hyperlinkRange, "https://example.com/");

        dynamic nativeRange = AppendParagraph(document, "x+y=1");
        document.OMaths.Add(nativeRange);
        nativeRange.OMaths.Item(1).BuildUp();

        AppendParagraph(document, @"安全区域之后的正常公式：$L=T-V$。");

        AppendHeading(document, "7. 跨段公式与续跑");
        AppendParagraph(
            document,
            "\\[\\begin{aligned}\r"
            + "\\delta S\r"
            + "&=\\int_{t_0}^{t_1}\\frac{\\partial L}{\\partial q}\\,\\delta q\\,\\mathrm dt\\\\\r"
            + "&\\quad+\\int_{t_0}^{t_1}\\frac{\\partial L}{\\partial\\dot q}\\,\\delta\\dot q\\,\\mathrm dt.\r"
            + "\\end{aligned}\\]");
        AppendParagraph(document, @"跨段公式之后：$\delta q(t_0)=\delta q(t_1)=0$。");

        AppendHeading(document, "8. 文档末尾边界");
        AppendParagraph(
            document,
            @"$$\mathcal E_i(L)=\frac{\partial L}{\partial q_i}-\frac{\mathrm d}{\mathrm dt}\left(\frac{\partial L}{\partial\dot q_i}\right)");
        AppendParagraph(document, @"未闭合行间公式之后仍可识别不同类型的末尾公式：\(E_{\mathrm{end}}=0\)");
    }

    private static void AppendTable(dynamic document)
    {
        dynamic range = EndRange(document);
        dynamic table = document.Tables.Add(range, 7, 3);
        table.AllowAutoFit = false;
        table.PreferredWidthType = WdPreferredWidthPoints;
        table.PreferredWidth = 468f;
        table.Columns.Item(1).Width = 78f;
        table.Columns.Item(2).Width = 260f;
        table.Columns.Item(3).Width = 130f;
        string[,] values =
        {
            { "位置", "内容", "预期" },
            { "A1", @"行内 $a+b$", "转换一个行内公式" },
            { "A2", @"$$c=d$$", "转换一个行间公式" },
            { "A3", @"前文 \[m\ddot q+kq=0\tag{T-3}\] 后文", "tag 映射手动编号" },
            { "B1", @"未闭合 $$\frac{\partial L}{\partial q}", "原文保留且不跨单元格" },
            { "B2", @"未闭合 \[\delta S=0", "原文保留且不跨单元格" },
            { "C3", @"正常公式 $H=\sum_i p_i\dot q_i-L$", "不受其他单元格影响" },
        };
        for (int row = 0; row < values.GetLength(0); row++)
        {
            for (int column = 0; column < values.GetLength(1); column++)
            {
                dynamic cell = table.Cell(row + 1, column + 1);
                cell.Range.Text = values[row, column];
                cell.VerticalAlignment = 1;
                cell.Range.Font.Size = 9.5f;
                if (row == 0)
                {
                    cell.Range.Font.Bold = 1;
                    cell.Shading.BackgroundPatternColor = 15132390;
                }
            }
        }

        dynamic after = document.Range(table.Range.End, table.Range.End);
        after.InsertParagraphAfter();
    }

    private static void ConfigureDocument(dynamic document)
    {
        dynamic section = document.Sections.Item(1);
        section.PageSetup.PageWidth = 612f;
        section.PageSetup.PageHeight = 792f;
        section.PageSetup.TopMargin = 72f;
        section.PageSetup.RightMargin = 72f;
        section.PageSetup.BottomMargin = 72f;
        section.PageSetup.LeftMargin = 72f;
        section.PageSetup.HeaderDistance = 35.4f;
        section.PageSetup.FooterDistance = 35.4f;

        dynamic header = section.Headers.Item(1).Range;
        header.Text = @"非主正文安全区域 $header$";

        dynamic normal = document.Styles.Item(-1);
        normal.Font.Name = "Calibri";
        normal.Font.NameFarEast = "Microsoft YaHei";
        normal.Font.Size = 11f;
        normal.Font.Color = 0;
        normal.ParagraphFormat.SpaceAfter = 6f;
        normal.ParagraphFormat.LineSpacingRule = WdLineSpaceMultiple;
        normal.ParagraphFormat.LineSpacing = 13.75f;
    }

    private static void AppendTitle(dynamic document, string text)
    {
        dynamic range = AppendParagraph(document, text);
        range.Font.Name = "Calibri";
        range.Font.NameFarEast = "Microsoft YaHei";
        range.Font.Size = 18f;
        range.Font.Bold = 1;
        range.Font.Color = 11943982;
        range.ParagraphFormat.SpaceAfter = 10f;
    }

    private static void AppendHeading(dynamic document, string text)
    {
        dynamic range = AppendParagraph(document, text);
        range.Font.Name = "Calibri";
        range.Font.NameFarEast = "Microsoft YaHei";
        range.Font.Size = 13f;
        range.Font.Bold = 1;
        range.Font.Color = 11943982;
        range.ParagraphFormat.SpaceBefore = 14f;
        range.ParagraphFormat.SpaceAfter = 7f;
    }

    private static dynamic AppendParagraph(dynamic document, string text)
    {
        int start = Convert.ToInt32(document.Content.End) - 1;
        dynamic range = document.Range(start, start);
        range.InsertAfter(text);
        int end = start + text.Length;
        dynamic textRange = document.Range(start, end);
        textRange.InsertParagraphAfter();
        return document.Range(start, end);
    }

    private static dynamic EndRange(dynamic document)
    {
        int end = Convert.ToInt32(document.Content.End) - 1;
        return document.Range(end, end);
    }
}
