using System;
using System.Globalization;
using System.IO;
using System.Xml.Linq;

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal static partial class MathTypeMtefCodec
{
    private sealed partial class MtefStructureReader
    {
        private double? _explicitSizePoints;

        private void ReadSizeRecord()
        {
            int start = _position;
            _position = SkipInitialSizeRecord(_data, start);
            byte form = _data[start + 1];
            if (form == 101)
            {
                double points = -BitConverter.ToInt16(_data, start + 2) / 32d;
                if (!(points > 0)) throw new InvalidDataException("Invalid explicit MTEF point size at " + start);
                _explicitSizePoints = points;
                return;
            }
            int logical = form == 100 ? _data[start + 2] : form;
            int delta = form == 100 ? BitConverter.ToInt16(_data, start + 3) : _data[start + 2] - 128;
            if (delta != 0 || logical > 4)
                throw new InvalidDataException("Unsupported MTEF logical size adjustment at " + start);
            _explicitSizePoints = null;
        }

        private void ApplyCurrentSize(XElement node)
        {
            if (_explicitSizePoints.HasValue)
                node.SetAttributeValue("mathsize", _explicitSizePoints.Value.ToString("0.#####", CultureInfo.InvariantCulture) + "pt");
        }
    }
}
