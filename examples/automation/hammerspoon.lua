-- Complete Hammerspoon workflow for clipboard images and copied image files.
-- Set these two paths, reload Hammerspoon, then press Ctrl+Alt+L.
local python = "/usr/bin/python3"
local client = "/absolute/path/to/examples/automation/local_client.py"
local mode = "formula"
local backend = "mathcraft"

local function decodeFileURL(value)
  local path = value and value:match("^file://(.+)$")
  if not path then return nil end
  return path:gsub("%%(%x%x)", function(hex)
    return string.char(tonumber(hex, 16))
  end)
end

local function clipboardFile()
  local url = hs.pasteboard.readURL()
  local path = type(url) == "string" and decodeFileURL(url) or nil
  if path and hs.fs.attributes(path, "mode") == "file" then return path, false end

  local text = hs.pasteboard.readString()
  if text and hs.fs.attributes(text, "mode") == "file" then return text, false end

  local image = hs.pasteboard.readImage()
  if not image then return nil, false end
  local temporaryBase = os.tmpname()
  os.remove(temporaryBase)
  local temporary = temporaryBase .. ".png"
  if not image:saveToFile(temporary, true, "png") then
    return nil, false
  end
  return temporary, true
end

local function recognizeClipboard()
  local path, temporary = clipboardFile()
  if not path then
    hs.notify.new({
      title = "LaTeXSnipper",
      informativeText = "Clipboard has no image data or existing image path.",
    }):send()
    return
  end

  local arguments = {
    client, path,
    "--backend", backend,
    "--mode", mode,
    "--output", "text",
  }
  local task = hs.task.new(python, function(exitCode, stdout, stderr)
    if temporary then os.remove(path) end
    if exitCode == 0 and stdout and stdout:match("%S") then
      hs.pasteboard.setContents(stdout:gsub("%s+$", ""))
      hs.notify.new({
        title = "LaTeXSnipper",
        informativeText = "Recognition copied to the clipboard.",
      }):send()
    else
      local detail = (stderr and stderr:match("%S") and stderr or "Recognition failed."):gsub("%s+$", "")
      hs.notify.new({title = "LaTeXSnipper", informativeText = detail}):send()
    end
  end, arguments)
  if not task or not task:start() then
    if temporary then os.remove(path) end
    hs.notify.new({
      title = "LaTeXSnipper",
      informativeText = "Could not start the Automation API client.",
    }):send()
  end
end

hs.hotkey.bind({"ctrl", "alt"}, "L", recognizeClipboard)
