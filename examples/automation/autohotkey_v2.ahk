#Requires AutoHotkey v2.0

; Ctrl+Alt+L recognizes the image file path currently stored in the clipboard.
^!l::{
    connectionPath := EnvGet("USERPROFILE") "\.latexsnipper\automation-api.json"
    connection := FileRead(connectionPath, "UTF-8")
    if !RegExMatch(connection, '"base_url":"([^"]+)"', &base) || !RegExMatch(connection, '"token":"([^"]+)"', &token)
        throw Error("Automation API connection file is invalid")
    boundary := "----LaTeXSnipper" A_TickCount
    image := FileRead(A_Clipboard, "RAW")
    prefix := "--" boundary "`r`nContent-Disposition: form-data; name=`"mode`"`r`n`r`nformula`r`n"
        . "--" boundary "`r`nContent-Disposition: form-data; name=`"images`"; filename=`"capture.png`"`r`n"
        . "Content-Type: application/octet-stream`r`n`r`n"
    suffix := "`r`n--" boundary "--`r`n"
    bodySize := StrPut(prefix, "UTF-8") - 1 + image.Size + StrPut(suffix, "UTF-8") - 1
    body := Buffer(bodySize + 1)
    offset := StrPut(prefix, body, "UTF-8") - 1
    DllCall("RtlMoveMemory", "Ptr", body.Ptr + offset, "Ptr", image.Ptr, "UPtr", image.Size)
    StrPut(suffix, body.Ptr + offset + image.Size, "UTF-8")
    body.Size := bodySize
    http := ComObject("WinHttp.WinHttpRequest.5.1")
    http.Open("POST", base[1] "/api/v1/recognition/jobs", false)
    http.SetRequestHeader("Authorization", "Bearer " token[1])
    http.SetRequestHeader("Content-Type", "multipart/form-data; boundary=" boundary)
    http.SetRequestHeader("Prefer", "wait=30")
    http.Send(body)
    if http.Status != 200 && http.Status != 202
        throw Error("Recognition failed: HTTP " http.Status)
    response := http.ResponseText
    deadline := A_TickCount + 150000
    while !RegExMatch(response, '"state":"(completed|failed|canceled)"', &state) {
        if !RegExMatch(response, '"id":"([^"]+)"', &job)
            throw Error("Recognition job id is missing")
        if A_TickCount >= deadline
            throw Error("Recognition timed out")
        Sleep(250)
        http.Open("GET", base[1] "/api/v1/recognition/jobs/" job[1], false)
        http.SetRequestHeader("Authorization", "Bearer " token[1])
        http.Send()
        if http.Status != 200
            throw Error("Recognition status failed: HTTP " http.Status)
        response := http.ResponseText
    }
    if state[1] != "completed"
        throw Error("Recognition failed: " state[1])
    if !RegExMatch(response, '"text":"((?:\\.|[^"])*)"', &result)
        throw Error("Recognition result is missing")
    text := StrReplace(result[1], '\"', '"')
    text := StrReplace(text, "\\", "\")
    text := StrReplace(text, "\n", "`n")
    A_Clipboard := text
}
