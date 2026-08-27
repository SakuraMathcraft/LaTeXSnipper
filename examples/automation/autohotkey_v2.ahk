#Requires AutoHotkey v2.0
#SingleInstance Force

; Ctrl+Alt+L accepts clipboard image data or a copied image-file path.
; The recognized formula is written back to the clipboard.
^!l::RecognizeClipboard()

RecognizeClipboard() {
    temporaryPath := ""
    try {
        source := ResolveClipboardImage()
        imagePath := source["path"]
        if source["temporary"]
            temporaryPath := imagePath
        connection := ReadConnection()
        response := SubmitImage(connection, imagePath, "mathcraft", "formula", 120)
        A_Clipboard := ResultText(response)
        TrayTip("Recognition copied to the clipboard.", "LaTeXSnipper")
    } catch Error as err {
        TrayTip(err.Message, "LaTeXSnipper Automation API", 3)
    } finally {
        if temporaryPath != "" && FileExist(temporaryPath)
            FileDelete(temporaryPath)
    }
}

ResolveClipboardImage() {
    clipboardText := Trim(Trim(A_Clipboard), Chr(34))
    if clipboardText != "" {
        attributes := FileExist(clipboardText)
        if attributes != "" && !InStr(attributes, "D")
            return Map("path", clipboardText, "temporary", false)
    }
    helper := A_ScriptDir "\clipboard_image.ps1"
    if !FileExist(helper)
        throw Error("Clipboard image helper is missing: " helper)
    outputPath := A_Temp "\latexsnipper-clipboard-" A_TickCount ".png"
    command := "powershell.exe -NoProfile -NonInteractive -STA -ExecutionPolicy Bypass -File "
        . QuoteArgument(helper) " -OutputPath " QuoteArgument(outputPath)
    exitCode := RunWait(command, , "Hide")
    if exitCode != 0 || !FileExist(outputPath) {
        if FileExist(outputPath)
            FileDelete(outputPath)
        throw Error("Clipboard does not contain image data or an existing image path.")
    }
    return Map("path", outputPath, "temporary", true)
}

ReadConnection() {
    path := EnvGet("USERPROFILE") "\.latexsnipper\automation-api.json"
    if !FileExist(path)
        throw Error("Automation API is disabled or its connection file is missing.")
    try connection := FileRead(path, "UTF-8")
    catch Error as err
        throw Error("Cannot read Automation API connection file: " err.Message)
    if !RegExMatch(connection, 'i)"base_url"\s*:\s*"([^"]+)"', &base)
        throw Error("Automation API connection file has no valid base_url.")
    if !RegExMatch(connection, 'i)"token"\s*:\s*"([^"]+)"', &token)
        throw Error("Automation API connection file has no valid token.")
    return Map("base_url", RTrim(base[1], "/"), "token", token[1])
}

SubmitImage(connection, imagePath, backend, mode, timeoutSeconds) {
    image := FileRead(imagePath, "RAW")
    if image.Size = 0
        throw Error("Clipboard image is empty.")
    boundary := "----LaTeXSnipper" A_TickCount "-" Random(100000, 999999)
    crlf := Chr(13) Chr(10)
    quote := Chr(34)
    prefix := MultipartField(boundary, "backend", backend)
        . MultipartField(boundary, "mode", mode)
        . MultipartField(boundary, "timeout", timeoutSeconds)
        . "--" boundary crlf
        . "Content-Disposition: form-data; name=" quote "images" quote
        . "; filename=" quote "capture.png" quote crlf
        . "Content-Type: " ImageContentType(imagePath) crlf crlf
    suffix := crlf "--" boundary "--" crlf
    bodySize := StrPut(prefix, "UTF-8") - 1 + image.Size + StrPut(suffix, "UTF-8") - 1
    body := Buffer(bodySize + 1)
    offset := StrPut(prefix, body, "UTF-8") - 1
    DllCall("RtlMoveMemory", "Ptr", body.Ptr + offset, "Ptr", image.Ptr, "UPtr", image.Size)
    StrPut(suffix, body.Ptr + offset + image.Size, "UTF-8")
    body.Size := bodySize

    http := ComObject("WinHttp.WinHttpRequest.5.1")
    http.SetTimeouts(5000, 5000, 35000, 40000)
    http.Open("POST", connection["base_url"] "/api/v1/recognition/jobs", false)
    http.SetRequestHeader("Authorization", "Bearer " connection["token"])
    http.SetRequestHeader("Content-Type", "multipart/form-data; boundary=" boundary)
    http.SetRequestHeader("Prefer", "wait=30")
    http.SetRequestHeader("Idempotency-Key", "ahk-" A_NowUTC "-" A_TickCount)
    try http.Send(BufferToByteArray(body))
    catch Error as err
        throw Error("Cannot connect to LaTeXSnipper Automation API: " err.Message)
    RequireHttpSuccess(http, "Recognition submission")

    response := http.ResponseText
    deadline := A_TickCount + (timeoutSeconds + 30) * 1000
    while !RegExMatch(response, 'i)"state"\s*:\s*"(completed|failed|canceled)"', &state) {
        if !RegExMatch(response, 'i)"id"\s*:\s*"([^"]+)"', &job)
            throw Error("Automation API response has no recognition job id.")
        if A_TickCount >= deadline
            throw Error("Recognition did not finish before the client timeout.")
        Sleep(250)
        http.Open("GET", connection["base_url"] "/api/v1/recognition/jobs/" job[1], false)
        http.SetRequestHeader("Authorization", "Bearer " connection["token"])
        try http.Send()
        catch Error as err
            throw Error("Cannot read recognition status: " err.Message)
        RequireHttpSuccess(http, "Recognition status")
        response := http.ResponseText
    }
    if state[1] != "completed"
        throw Error("Recognition ended with state " state[1] ": " ApiMessage(response))
    return response
}

BufferToByteArray(buffer) {
    byteArray := ComObjArray(0x11, buffer.Size) ; VT_ARRAY | VT_UI1
    data := 0
    result := DllCall(
        "OleAut32\SafeArrayAccessData",
        "Ptr", byteArray.Ptr,
        "Ptr*", &data,
        "HRESULT"
    )
    if result != 0
        throw OSError(result, "SafeArrayAccessData")
    try DllCall("RtlMoveMemory", "Ptr", data, "Ptr", buffer.Ptr, "UPtr", buffer.Size)
    finally DllCall("OleAut32\SafeArrayUnaccessData", "Ptr", byteArray.Ptr)
    return byteArray
}

MultipartField(boundary, name, value) {
    crlf := Chr(13) Chr(10)
    quote := Chr(34)
    return "--" boundary crlf
        . "Content-Disposition: form-data; name=" quote name quote crlf crlf
        . value crlf
}

ImageContentType(path) {
    SplitPath(path, , , &extension)
    extension := StrLower(extension)
    types := Map(
        "png", "image/png", "jpg", "image/jpeg", "jpeg", "image/jpeg",
        "bmp", "image/bmp", "gif", "image/gif", "tif", "image/tiff",
        "tiff", "image/tiff", "webp", "image/webp"
    )
    return types.Has(extension) ? types[extension] : "application/octet-stream"
}

RequireHttpSuccess(http, action) {
    if http.Status != 200 && http.Status != 202
        throw Error(action " failed: HTTP " http.Status ": " ApiMessage(http.ResponseText))
}

ApiMessage(response) {
    if RegExMatch(response, 'i)"message"\s*:\s*"((?:\\.|[^"])*)"', &match)
        return JsonUnescape(match[1])
    return "No error message was returned."
}

ResultText(response) {
    if !RegExMatch(response, 'i)"text"\s*:\s*"((?:\\.|[^"])*)"', &result)
        throw Error("Completed recognition response contains no text result.")
    return JsonUnescape(result[1])
}

JsonUnescape(value) {
    result := ""
    index := 1
    length := StrLen(value)
    while index <= length {
        character := SubStr(value, index, 1)
        if character != "\" {
            result .= character
            index += 1
            continue
        }
        index += 1
        if index > length {
            result .= "\"
            break
        }
        escaped := SubStr(value, index, 1)
        switch escaped {
            case Chr(34): result .= Chr(34)
            case "\": result .= "\"
            case "/": result .= "/"
            case "b": result .= Chr(8)
            case "f": result .= Chr(12)
            case "n": result .= Chr(10)
            case "r": result .= Chr(13)
            case "t": result .= Chr(9)
            case "u":
                hex := SubStr(value, index + 1, 4)
                if RegExMatch(hex, "i)^[0-9a-f]{4}$") {
                    result .= Chr("0x" hex)
                    index += 4
                } else {
                    result .= "\u"
                }
            default: result .= escaped
        }
        index += 1
    }
    return result
}

QuoteArgument(value) {
    return Chr(34) StrReplace(value, Chr(34), "\" Chr(34)) Chr(34)
}
