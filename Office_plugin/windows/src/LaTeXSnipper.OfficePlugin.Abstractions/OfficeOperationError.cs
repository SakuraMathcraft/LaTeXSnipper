using System;
using System.Globalization;
using System.Reflection;
using System.Runtime.InteropServices;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public static class OfficeOperationError
{
    public static string Describe(Exception exception)
    {
        if (exception == null)
        {
            throw new ArgumentNullException(nameof(exception));
        }

        Exception cause = exception;
        while (cause.InnerException != null
            && (cause is TargetInvocationException
                || cause is AggregateException aggregate && aggregate.InnerExceptions.Count == 1))
        {
            cause = cause.InnerException;
        }
        string message = cause.Message.Trim();
        string detail = string.IsNullOrEmpty(message) ? cause.GetType().Name : message;
        if (cause.GetBaseException() is COMException comException)
        {
            detail += " (HRESULT 0x" + comException.ErrorCode.ToString("X8", CultureInfo.InvariantCulture) + ")";
        }

        bool localized = false;
        foreach (char value in detail)
        {
            if (value >= '\u3400' && value <= '\u9fff')
            {
                localized = true;
                break;
            }
        }

        if (cause is TimeoutException)
        {
            return "操作超时：" + detail;
        }

        return localized ? detail : "操作失败：" + detail;
    }
}
