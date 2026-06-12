using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private void DeleteFormula(SelectedWordFormula selected)
    {
        if (selected.IsOleInlineShape)
        {
            DeleteOleInlineShape(selected);
            return;
        }

        dynamic control = selected.ContentControl;
        string equationId = selected.Metadata.Identity.EquationId;
        object? metadataControl = TryGetMetadataControlById(_wordApplication.ActiveDocument, equationId);
        if (selected.Metadata.NumberingMode != NumberingMode.None)
        {
            DeleteNumberedFormulaById(equationId);
            DeleteMetadataControl(metadataControl);
            return;
        }

        control.Delete(true);
        DeleteMetadataControl(metadataControl);
    }

    private void DeleteOleInlineShape(SelectedWordFormula selected)
    {
        string equationId = selected.Metadata.Identity.EquationId;
        dynamic inlineShape = selected.ContentControl;
        object? numberControl = TryGetNumberControlById(_wordApplication.ActiveDocument, equationId);
        if (numberControl != null)
        {
            DeleteNumberedFormulaById(equationId);
            return;
        }

        inlineShape.Delete();
    }

    private void DeleteNumberedFormulaById(string equationId)
    {
        var targets = new List<DeletionTarget>();
        object? equationControl = TryGetEquationControlById(equationId);
        object? numberControl = TryGetNumberControlById(_wordApplication.ActiveDocument, equationId);
        object? oleInlineShape = TryFindOleInlineShapeById(equationId);
        if (equationControl != null)
        {
            AddContentControlDeletionTarget(targets, equationControl);
        }

        if (numberControl != null)
        {
            AddContentControlDeletionTarget(targets, numberControl);
        }

        if (oleInlineShape != null)
        {
            AddOleDeletionTarget(targets, oleInlineShape);
        }

        DeleteTargetsInDocumentOrder(targets);
    }

    private void AddContentControlDeletionTarget(ICollection<DeletionTarget> targets, object control)
    {
        dynamic item = control;
        AddAdjacentTabDeletionTargets(targets, item.Range);
        int start = GetRangeStart(item.Range);
        int end = GetRangeEnd(item.Range);
        Action delete = () => item.Delete(true);
        targets.Add(new DeletionTarget(start, end, delete));
    }

    private void AddOleDeletionTarget(ICollection<DeletionTarget> targets, object inlineShape)
    {
        dynamic item = inlineShape;
        AddAdjacentTabDeletionTargets(targets, item.Range);
        int start = GetRangeStart(item.Range);
        int end = GetRangeEnd(item.Range);
        Action delete = () => item.Delete();
        targets.Add(new DeletionTarget(start, end, delete));
    }

    private void AddAdjacentTabDeletionTargets(ICollection<DeletionTarget> targets, dynamic range)
    {
        int start = GetRangeStart(range);
        int end = GetRangeEnd(range);
        AddTabDeletionTarget(targets, start - 1, start);
        AddTabDeletionTarget(targets, end, end + 1);
    }

    private void AddTabDeletionTarget(ICollection<DeletionTarget> targets, int start, int end)
    {
        int safeStart = ClampDocumentPosition(start);
        int safeEnd = ClampDocumentPosition(end);
        if (safeEnd <= safeStart)
        {
            return;
        }

        dynamic range = CreateDocumentRange(safeStart, safeEnd);
        string text = Convert.ToString(range.Text) ?? string.Empty;
        if (text == "\t")
        {
            targets.Add(new DeletionTarget(safeStart, safeEnd, () => CreateDocumentRange(safeStart, safeEnd).Delete()));
        }
    }

    private static void DeleteTargetsInDocumentOrder(List<DeletionTarget> targets)
    {
        targets.Sort((left, right) => right.Start.CompareTo(left.Start));
        var deleted = new HashSet<string>(StringComparer.Ordinal);
        foreach (DeletionTarget target in targets)
        {
            string key = target.Start.ToString(System.Globalization.CultureInfo.InvariantCulture) + ":" +
                target.End.ToString(System.Globalization.CultureInfo.InvariantCulture);
            if (deleted.Add(key))
            {
                target.Delete();
            }
        }
    }

    private static void DeleteMetadataControl(object? metadataControl)
    {
        if (metadataControl == null)
        {
            return;
        }

        dynamic backup = metadataControl;
        backup.Delete(true);
    }

    private static int GetFormulaStart(SelectedWordFormula formula)
    {
        try
        {
            return Convert.ToInt32(((dynamic)formula.ContentControl).Range.Start);
        }
        catch
        {
            return 0;
        }
    }
}
