using System;
using System.Collections.Generic;
using System.Linq;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal static class E2EAssert
{
    public static void Equal<T>(T expected, T actual, string description)
    {
        if (!EqualityComparer<T>.Default.Equals(expected, actual))
        {
            throw new InvalidOperationException(
                description + ": expected " + expected + ", actual " + actual + ".");
        }
    }

    public static void True(bool condition, string description)
    {
        if (!condition)
        {
            throw new InvalidOperationException(description + ".");
        }
    }

    public static void SetEqual(
        IEnumerable<string> expected,
        IEnumerable<string> actual,
        string description)
    {
        string[] expectedValues = expected.OrderBy(value => value, StringComparer.Ordinal).ToArray();
        string[] actualValues = actual.OrderBy(value => value, StringComparer.Ordinal).ToArray();
        if (!expectedValues.SequenceEqual(actualValues, StringComparer.Ordinal))
        {
            throw new InvalidOperationException(
                description
                + ": expected ["
                + string.Join(", ", expectedValues)
                + "], actual ["
                + string.Join(", ", actualValues)
                + "].");
        }
    }
}
