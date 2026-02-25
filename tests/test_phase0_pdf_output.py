import unittest
from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.pdf_output_contract import wrap_document_output


class Phase0PdfOutputTests(unittest.TestCase):
    def test_empty_content_returns_empty(self):
        self.assertEqual(wrap_document_output("", "markdown", "paper"), "")
        self.assertEqual(wrap_document_output("   ", "latex", "journal"), "")

    def test_markdown_paper_template(self):
        out = wrap_document_output("A+B=C", "markdown", "paper")
        self.assertIn("# Title", out)
        self.assertIn("## Abstract", out)
        self.assertIn("## References", out)
        self.assertIn("A+B=C", out)

    def test_latex_existing_document_pass_through(self):
        src = "\\documentclass{article}\n\\begin{document}\nX\n\\end{document}"
        out = wrap_document_output(src, "latex", "paper")
        self.assertEqual(out, src)

    def test_latex_journal_template(self):
        out = wrap_document_output("E=mc^2", "latex", "journal")
        self.assertIn("\\documentclass[journal]{IEEEtran}", out)
        self.assertIn("\\begin{document}", out)
        self.assertIn("E=mc^2", out)
        self.assertTrue(out.rstrip().endswith("\\end{document}"))


if __name__ == "__main__":
    unittest.main()
