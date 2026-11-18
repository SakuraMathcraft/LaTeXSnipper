using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private void SaveFormulaMetadata(FormulaMetadata metadata)
    {
        object? equationControl = TryGetEquationControlById(metadata.Identity.EquationId);
        if (equationControl != null)
        {
            SaveFormulaMetadata(equationControl, metadata);
            return;
        }

        object? inlineShape = TryFindOleInlineShapeById(metadata.Identity.EquationId);
        if (inlineShape == null)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
        }

        SaveFormulaMetadata(inlineShape, metadata);
    }

    private void SaveFormulaMetadata(object formulaObject, FormulaMetadata metadata)
    {
        dynamic shape = formulaObject;
        if (metadata.RenderEngine == RenderEngineKind.Omml)
        {
            string tag = WordFormulaMetadataStore.Save(
                CurrentDocument,
                metadata);
            shape.Tag = tag;
            TryCom(() => shape.Title = "LaTeXSnipper Equation");
            FormulaMetadata stored = WordFormulaMetadataStore.Load(
                CurrentDocument,
                Convert.ToString(shape.Tag) ?? string.Empty);
            if (!string.Equals(
                    stored.Identity.EquationId,
                    metadata.Identity.EquationId,
                    StringComparison.Ordinal))
            {
                throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
            }

            return;
        }

        OleFormulaContent.UpdateNumbering((object)shape, metadata);
        shape.AlternativeText = WordFormulaMetadataStore.Save(
            CurrentDocument,
            metadata);
    }

    private FormulaMetadata LoadFormulaMetadata(
        dynamic control,
        string equationId,
        RenderEngineKind actualRenderEngine)
    {
        if (actualRenderEngine == RenderEngineKind.MathJaxSvg)
            return OleFormulaContent.Read((object)control).Metadata(
                WordFormulaMetadataStore.LoadOleIdentity(CurrentDocument, ReadFormulaObjectTag(control)));
        FormulaMetadata metadata = WordFormulaMetadataStore.Load(
            CurrentDocument,
            ReadFormulaObjectTag(control));
        if (!string.Equals(metadata.Identity.EquationId, equationId, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        if (metadata.RenderEngine != actualRenderEngine)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        return metadata;
    }

    private static string ReadFormulaObjectTag(dynamic formulaObject)
    {
        try
        {
            return Convert.ToString(formulaObject.AlternativeText) ?? string.Empty;
        }
        catch
        {
            return Convert.ToString(formulaObject.Tag) ?? string.Empty;
        }
    }

    private static FormulaMetadata WithRenderEngine(FormulaMetadata metadata, RenderEngineKind renderEngine)
    {
        return new FormulaMetadata(
            metadata.Identity,
            metadata.Latex,
            metadata.DisplayMode,
            metadata.NumberingMode,
            metadata.NumberText,
            renderEngine,
            metadata.SchemaVersion,
            metadata.Typography);
    }

    private static FormulaMetadata WithNewIdentity(FormulaMetadata metadata, string documentId)
    {
        return new FormulaMetadata(
            new FormulaIdentity(documentId, Guid.NewGuid().ToString("N")),
            metadata.Latex,
            metadata.DisplayMode,
            metadata.NumberingMode,
            metadata.NumberText,
            metadata.RenderEngine,
            metadata.SchemaVersion,
            metadata.Typography);
    }

    private static string ReadControlTag(dynamic control)
    {
        try
        {
            return Convert.ToString(control.Tag) ?? string.Empty;
        }
        catch
        {
            return string.Empty;
        }
    }

    private object? TryGetEquationControlById(string equationId)
    {
        try
        {
            dynamic controls = CurrentDocument.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                if (GetEquationControlId(control) == equationId)
                {
                    return control;
                }
            }
        }
        catch
        {
        }

        return null;
    }

    private dynamic CreateDocumentRange(int start, int end)
    {
        try
        {
            return CurrentDocument.Range(start, end);
        }
        catch
        {
            return CurrentDocument.Range(Math.Max(0, start - 1), Math.Max(0, end - 1));
        }
    }

    private int ClampDocumentPosition(int position)
    {
        try
        {
            int documentStart = Convert.ToInt32(CurrentDocument.Content.Start);
            int documentEnd = Convert.ToInt32(CurrentDocument.Content.End);
            return Math.Min(Math.Max(position, documentStart), documentEnd);
        }
        catch
        {
            return Math.Max(0, position);
        }
    }

    private static int GetRangeEnd(dynamic range)
    {
        return Convert.ToInt32(range.End);
    }

    private static int GetRangeStart(dynamic range)
    {
        return Convert.ToInt32(range.Start);
    }

    private static bool RangesOverlap(int leftStart, int leftEnd, int rightStart, int rightEnd)
    {
        return leftStart < rightEnd && leftEnd > rightStart;
    }

    private static bool IsCollapsedRange(dynamic range)
    {
        try
        {
            return Convert.ToInt32(range.Start) == Convert.ToInt32(range.End);
        }
        catch
        {
            return false;
        }
    }

    private static bool RangeTouchesManagedFormula(dynamic range)
    {
        return TryGetParentContentControl(range) != null
            || TryGetFirstManagedContentControl(range) != null;
    }
}
