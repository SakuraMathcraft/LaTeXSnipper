using System;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal static class WordFormulaColorDefaults
{
    private const string PersonalizeRegistryPath =
        @"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize";
    private const string AppsUseLightThemeValue = "AppsUseLightTheme";

    public static string Current => IsDarkMode() ? "#FFFFFF" : "#000000";

    private static bool IsDarkMode()
    {
        using RegistryKey? key = Registry.CurrentUser.OpenSubKey(PersonalizeRegistryPath);
        object? value = key?.GetValue(AppsUseLightThemeValue);
        return value != null && Convert.ToInt32(value) == 0;
    }
}
