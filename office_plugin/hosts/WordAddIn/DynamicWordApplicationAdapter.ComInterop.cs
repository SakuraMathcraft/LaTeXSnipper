using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private void ExecuteWithScreenUpdatingSuspended(Action action)
    {
        bool restore = false;
        bool original = true;
        bool undoRecordStarted = false;
        try
        {
            original = Convert.ToBoolean(_wordApplication.ScreenUpdating);
            restore = true;
            _wordApplication.ScreenUpdating = false;
        }
        catch
        {
        }

        try
        {
            if (_undoRecordDepth == 0)
            {
                undoRecordStarted = TryStartUndoRecord();
            }

            action();
        }
        finally
        {
            if (undoRecordStarted)
            {
                TryEndUndoRecord();
            }

            if (restore)
            {
                TryCom(() => _wordApplication.ScreenUpdating = original);
            }
        }
    }

    private bool TryStartUndoRecord()
    {
        try
        {
            dynamic undoRecord = _wordApplication.UndoRecord;
            undoRecord.StartCustomRecord("LaTeXSnipper");
            return true;
        }
        catch
        {
            return false;
        }
    }

    private void TryEndUndoRecord()
    {
        TryCom(() => _wordApplication.UndoRecord.EndCustomRecord());
    }

    private static void TryCom(Action action)
    {
        try
        {
            action();
        }
        catch
        {
        }
    }

    private static object? TryGetParentContentControl(dynamic range)
    {
        try
        {
            dynamic control = range.ParentContentControl;
            return IsManagedControl(control) ? control : null;
        }
        catch
        {
            return null;
        }
    }

    private static object? TryGetFirstManagedContentControl(dynamic range)
    {
        try
        {
            dynamic controls = range.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                if (IsManagedControl(control))
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

    private static bool IsManagedControl(dynamic control)
    {
        try
        {
            return !string.IsNullOrWhiteSpace(GetManagedEquationId(control));
        }
        catch
        {
            return false;
        }
    }

    private static string GetEquationId(dynamic control)
    {
        return GetManagedEquationId(control);
    }

    private static string GetEquationControlId(dynamic control)
    {
        string tag = Convert.ToString(control.Tag) ?? string.Empty;
        return WordFormulaMetadataStore.EquationIdFromTag(tag);
    }

    private static string GetManagedEquationId(dynamic control)
    {
        string tag = Convert.ToString(control.Tag) ?? string.Empty;
        string equationId = WordFormulaMetadataStore.EquationIdFromTag(tag);
        if (!string.IsNullOrWhiteSpace(equationId))
        {
            return equationId;
        }

        equationId = WordFormulaMetadataStore.EquationIdFromNumberTag(tag);
        return string.IsNullOrWhiteSpace(equationId)
            ? WordFormulaMetadataStore.EquationIdFromMetadataTag(tag)
            : equationId;
    }

    private static string GetOleInlineShapeEquationId(dynamic inlineShape)
    {
        try
        {
            string tag = Convert.ToString(inlineShape.AlternativeText) ?? string.Empty;
            return WordFormulaMetadataStore.EquationIdFromTag(tag);
        }
        catch
        {
            return string.Empty;
        }
    }

    private static bool IsEquationControl(dynamic control)
    {
        try
        {
            string tag = Convert.ToString(control.Tag) ?? string.Empty;
            return !string.IsNullOrWhiteSpace(WordFormulaMetadataStore.EquationIdFromTag(tag));
        }
        catch
        {
            return false;
        }
    }

    private static void ValidateManagedEquationInput(string ooxml, FormulaMetadata metadata)
    {
        if (string.IsNullOrWhiteSpace(ooxml))
        {
            throw new ArgumentException("OOXML is required.", nameof(ooxml));
        }

        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }
    }
}
