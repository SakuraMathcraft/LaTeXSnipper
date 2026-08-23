-- Recognize an image file copied in Finder. Configure Python path as needed.
hs.hotkey.bind({"ctrl", "alt"}, "L", function()
  local path = hs.pasteboard.getContents()
  hs.task.new("/usr/bin/python3", nil, {"/path/to/examples/automation/local_client.py", path}):start()
end)
