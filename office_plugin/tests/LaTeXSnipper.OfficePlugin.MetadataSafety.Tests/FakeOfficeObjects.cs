using System;
using System.Collections.Generic;

namespace LaTeXSnipper.OfficePlugin.MetadataSafety.Tests;

public sealed class FakeOfficeVariable
{
    public FakeOfficeVariable(string value)
    {
        Value = value;
    }

    public string Value { get; set; }
}

public sealed class FakeOfficeVariables
{
    private readonly Dictionary<string, FakeOfficeVariable> _variables =
        new Dictionary<string, FakeOfficeVariable>(StringComparer.Ordinal);

    public FakeOfficeVariable Item(string name)
    {
        if (_variables.TryGetValue(name, out FakeOfficeVariable? variable))
        {
            return variable;
        }

        throw new InvalidOperationException("Variable not found: " + name);
    }

    public FakeOfficeVariable Add(string name, string value)
    {
        var variable = new FakeOfficeVariable(value);
        _variables[name] = variable;
        return variable;
    }
}

public sealed class FakeWordDocument
{
    public FakeOfficeVariables Variables { get; } = new FakeOfficeVariables();
}

public sealed class FakeOfficeProperty
{
    public FakeOfficeProperty(string value)
    {
        Value = value;
    }

    public string Value { get; set; }
}

public sealed class FakeOfficeProperties
{
    private readonly Dictionary<string, FakeOfficeProperty> _properties =
        new Dictionary<string, FakeOfficeProperty>(StringComparer.Ordinal);

    public FakeOfficeProperty Item(string name)
    {
        if (_properties.TryGetValue(name, out FakeOfficeProperty? property))
        {
            return property;
        }

        throw new InvalidOperationException("Property not found: " + name);
    }

    public FakeOfficeProperty Add(string name, bool linkToContent, int propertyType, string value)
    {
        _ = linkToContent;
        _ = propertyType;
        var property = new FakeOfficeProperty(value);
        _properties[name] = property;
        return property;
    }
}

public sealed class FakePowerPointPresentation
{
    public FakeOfficeProperties CustomDocumentProperties { get; } = new FakeOfficeProperties();
}

public sealed class FakeShapeTags
{
    private readonly Dictionary<string, string> _values =
        new Dictionary<string, string>(StringComparer.Ordinal);

    public string this[string name] =>
        _values.TryGetValue(name, out string? value) ? value : string.Empty;

    public void Add(string name, string value)
    {
        _values[name] = value;
    }

    public void Remove(string name)
    {
        _values.Remove(name);
    }
}

public sealed class FakePowerPointShape
{
    public string AlternativeText { get; set; } = string.Empty;

    public FakeShapeTags Tags { get; } = new FakeShapeTags();
}
