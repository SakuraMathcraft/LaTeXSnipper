using System;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal static class WordFormulaColorDefaults
{
    private const string PersonalizeRegistryPath =
        @"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize";
    private const string AppsUseLightThemeValue = "AppsUseLightTheme";
    private const string OfficeThemeRegistryPath = @"Software\Microsoft\Office\16.0\Common";
    private const string OfficeThemeValue = "UI Theme";

    public static string Current => IsDarkMode() ? "#FFFFFF" : "#000000";

    private static bool IsDarkMode()
    {
        using RegistryKey? officeKey = Registry.CurrentUser.OpenSubKey(OfficeThemeRegistryPath);
        object? officeTheme = officeKey?.GetValue(OfficeThemeValue);
        if (officeTheme != null && Convert.ToInt32(officeTheme) == 2)
        {
            return true;
        }

        using RegistryKey? key = Registry.CurrentUser.OpenSubKey(PersonalizeRegistryPath);
        object? value = key?.GetValue(AppsUseLightThemeValue);
        return value != null && Convert.ToInt32(value) == 0;
    }
}
