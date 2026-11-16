#if NET48
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Globalization;

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal static class SvgPathDataParser
{
    public static GraphicsPath Parse(string data)
    {
        var tokenizer = new Tokenizer(data);
        var path = new GraphicsPath(FillMode.Winding);
        PointF current = PointF.Empty;
        PointF start = PointF.Empty;
        PointF lastQuadraticControl = PointF.Empty;
        PointF lastCubicControl = PointF.Empty;
        bool lastWasQuadratic = false;
        bool lastWasCubic = false;
        char command = '\0';

        while (tokenizer.HasMore)
        {
            if (tokenizer.TryReadCommand(out char explicitCommand))
            {
                command = explicitCommand;
            }

            bool relative = char.IsLower(command);
            char normalized = char.ToUpperInvariant(command);
            switch (normalized)
            {
                case 'M':
                    current = ReadPoint(tokenizer, current, relative);
                    start = current;
                    path.StartFigure();
                    lastWasQuadratic = false;
                    lastWasCubic = false;
                    while (tokenizer.NextIsNumber)
                    {
                        PointF point = ReadPoint(tokenizer, current, relative);
                        path.AddLine(current, point);
                        current = point;
                    }

                    break;
                case 'L':
                    while (tokenizer.NextIsNumber)
                    {
                        PointF point = ReadPoint(tokenizer, current, relative);
                        path.AddLine(current, point);
                        current = point;
                    }

                    lastWasQuadratic = false;
                    lastWasCubic = false;
                    break;
                case 'H':
                    while (tokenizer.NextIsNumber)
                    {
                        float x = tokenizer.ReadNumber();
                        if (relative)
                        {
                            x += current.X;
                        }

                        var point = new PointF(x, current.Y);
                        path.AddLine(current, point);
                        current = point;
                    }

                    lastWasQuadratic = false;
                    lastWasCubic = false;
                    break;
                case 'V':
                    while (tokenizer.NextIsNumber)
                    {
                        float y = tokenizer.ReadNumber();
                        if (relative)
                        {
                            y += current.Y;
                        }

                        var point = new PointF(current.X, y);
                        path.AddLine(current, point);
                        current = point;
                    }

                    lastWasQuadratic = false;
                    lastWasCubic = false;
                    break;
                case 'Q':
                    while (tokenizer.NextIsNumber)
                    {
                        PointF control = ReadPoint(tokenizer, current, relative);
                        PointF end = ReadPoint(tokenizer, current, relative);
                        AddQuadratic(path, current, control, end);
                        current = end;
                        lastQuadraticControl = control;
                    }

                    lastWasQuadratic = true;
                    lastWasCubic = false;
                    break;
                case 'T':
                    while (tokenizer.NextIsNumber)
                    {
                        PointF control = lastWasQuadratic ? Reflect(current, lastQuadraticControl) : current;
                        PointF end = ReadPoint(tokenizer, current, relative);
                        AddQuadratic(path, current, control, end);
                        current = end;
                        lastQuadraticControl = control;
                        lastWasQuadratic = true;
                    }

                    lastWasCubic = false;
                    break;
                case 'C':
                    while (tokenizer.NextIsNumber)
                    {
                        PointF control1 = ReadPoint(tokenizer, current, relative);
                        PointF control2 = ReadPoint(tokenizer, current, relative);
                        PointF end = ReadPoint(tokenizer, current, relative);
                        path.AddBezier(current, control1, control2, end);
                        current = end;
                        lastCubicControl = control2;
                    }

                    lastWasQuadratic = false;
                    lastWasCubic = true;
                    break;
                case 'S':
                    while (tokenizer.NextIsNumber)
                    {
                        PointF control1 = lastWasCubic ? Reflect(current, lastCubicControl) : current;
                        PointF control2 = ReadPoint(tokenizer, current, relative);
                        PointF end = ReadPoint(tokenizer, current, relative);
                        path.AddBezier(current, control1, control2, end);
                        current = end;
                        lastCubicControl = control2;
                        lastWasCubic = true;
                    }

                    lastWasQuadratic = false;
                    break;
                case 'Z':
                    path.CloseFigure();
                    current = start;
                    lastWasQuadratic = false;
                    lastWasCubic = false;
                    break;
                default:
                    throw new NotSupportedException("Unsupported SVG path command: " + command);
            }
        }

        return path;
    }

    private static PointF ReadPoint(Tokenizer tokenizer, PointF current, bool relative)
    {
        float x = tokenizer.ReadNumber();
        float y = tokenizer.ReadNumber();
        if (relative)
        {
            return new PointF(current.X + x, current.Y + y);
        }

        return new PointF(x, y);
    }

    private static void AddQuadratic(GraphicsPath path, PointF start, PointF control, PointF end)
    {
        var control1 = new PointF(
            start.X + (2f / 3f) * (control.X - start.X),
            start.Y + (2f / 3f) * (control.Y - start.Y));
        var control2 = new PointF(
            end.X + (2f / 3f) * (control.X - end.X),
            end.Y + (2f / 3f) * (control.Y - end.Y));
        path.AddBezier(start, control1, control2, end);
    }

    private static PointF Reflect(PointF current, PointF control)
    {
        return new PointF((2 * current.X) - control.X, (2 * current.Y) - control.Y);
    }

    private sealed class Tokenizer
    {
        private readonly string _data;
        private int _index;

        public Tokenizer(string data)
        {
            _data = data ?? string.Empty;
        }

        public bool HasMore
        {
            get
            {
                SkipSeparators();
                return _index < _data.Length;
            }
        }

        public bool NextIsNumber
        {
            get
            {
                SkipSeparators();
                if (_index >= _data.Length)
                {
                    return false;
                }

                char c = _data[_index];
                return c == '-' || c == '+' || c == '.' || char.IsDigit(c);
            }
        }

        public bool TryReadCommand(out char command)
        {
            SkipSeparators();
            if (_index < _data.Length && char.IsLetter(_data[_index]))
            {
                command = _data[_index++];
                return true;
            }

            command = '\0';
            return false;
        }

        public float ReadNumber()
        {
            SkipSeparators();
            int start = _index;
            if (_index < _data.Length && (_data[_index] == '+' || _data[_index] == '-'))
            {
                _index++;
            }

            while (_index < _data.Length && char.IsDigit(_data[_index]))
            {
                _index++;
            }

            if (_index < _data.Length && _data[_index] == '.')
            {
                _index++;
                while (_index < _data.Length && char.IsDigit(_data[_index]))
                {
                    _index++;
                }
            }

            if (_index < _data.Length && (_data[_index] == 'e' || _data[_index] == 'E'))
            {
                _index++;
                if (_index < _data.Length && (_data[_index] == '+' || _data[_index] == '-'))
                {
                    _index++;
                }

                while (_index < _data.Length && char.IsDigit(_data[_index]))
                {
                    _index++;
                }
            }

            if (start == _index)
            {
                throw new FormatException("Expected an SVG path number.");
            }

            return float.Parse(_data.Substring(start, _index - start), NumberStyles.Float, CultureInfo.InvariantCulture);
        }

        private void SkipSeparators()
        {
            while (_index < _data.Length && (char.IsWhiteSpace(_data[_index]) || _data[_index] == ','))
            {
                _index++;
            }
        }
    }
}
#endif
