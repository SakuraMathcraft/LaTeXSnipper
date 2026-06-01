using System;
using System.Drawing;
using System.Windows.Forms;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

internal sealed class OlePayloadEditForm : Form
{
    private readonly TextBox _latexBox = new TextBox();

    public OlePayloadEditForm(string latex)
    {
        Text = "LaTeXSnipper Formula";
        Width = 720;
        Height = 420;
        StartPosition = FormStartPosition.CenterScreen;

        var label = new Label
        {
            Text = "LaTeX",
            Dock = DockStyle.Top,
            Height = 28,
            TextAlign = ContentAlignment.MiddleLeft
        };
        _latexBox.Multiline = true;
        _latexBox.Dock = DockStyle.Fill;
        _latexBox.Font = new Font("Consolas", 12f);
        _latexBox.Text = latex;

        var buttons = new FlowLayoutPanel
        {
            Dock = DockStyle.Bottom,
            FlowDirection = FlowDirection.RightToLeft,
            Height = 48
        };
        var ok = new Button { Text = "OK", DialogResult = DialogResult.OK, Width = 100 };
        var cancel = new Button { Text = "Cancel", DialogResult = DialogResult.Cancel, Width = 100 };
        buttons.Controls.Add(ok);
        buttons.Controls.Add(cancel);

        Controls.Add(_latexBox);
        Controls.Add(label);
        Controls.Add(buttons);
        AcceptButton = ok;
        CancelButton = cancel;
    }

    public string Latex => _latexBox.Text;
}
