let mathfield = null;
let bridge = null;
let currentKeyboardHeight = 0;

function setThemeMode(mode) {
  document.body.dataset.theme = mode === 'light' ? 'light' : 'dark';
}

function syncKeyboardState() {
  const vk = window.mathVirtualKeyboard;
  const visible = !!vk?.visible;
  document.body.classList.toggle('vk-visible', visible);
  const rawHeight =
    vk?.boundingRect?.height ||
    vk?.element?.getBoundingClientRect?.().height ||
    0;
  currentKeyboardHeight = visible ? Math.max(180, Math.min(rawHeight || 240, 380)) : 0;
}

function reportPreferredHeight() {
  if (!bridge || typeof bridge.onMathLiveHeightChanged !== 'function') return;
  const editorHeight = 96;
  const preferred = Math.max(120, Math.min(560, editorHeight + currentKeyboardHeight + 12));
  try {
    bridge.onMathLiveHeightChanged(preferred);
  } catch (_) {
    // Ignore bridge height sync errors.
  }
}

function syncLayout() {
  const host = document.getElementById('mathfield-host');
  if (!host || !mathfield) return;
  host.style.minHeight = '0px';
  host.style.maxHeight = 'none';
  host.style.flex = '1 1 auto';
  mathfield.style.minHeight = '100%';
  mathfield.style.height = '100%';
  mathfield.style.maxHeight = 'none';
  reportPreferredHeight();
}

function ensureKeyboardVisible() {
  const vk = window.mathVirtualKeyboard;
  if (!vk) return;
  try {
    vk.container = document.body;
    const keyboardHeight = Math.max(180, Math.min(380, Math.floor(window.innerHeight * 0.52)));
    vk.boundingRect = {
      left: 0,
      top: Math.max(0, window.innerHeight - keyboardHeight),
      width: window.innerWidth,
      height: keyboardHeight,
    };
    vk.visible = true;
    syncKeyboardState();
    syncLayout();
  } catch (_) {
    // Ignore keyboard visibility errors.
  }
}

function currentLatex() {
  return mathfield?.getValue('latex-expanded')?.trim() || '';
}

function clearMathfield() {
  if (!mathfield) return;
  mathfield.setValue('', { silenceNotifications: true });
  syncLayout();
  mathfield.focus();
}

function focusMathfield(showKeyboard = true) {
  if (!mathfield) return;
  mathfield.focus();
  if (showKeyboard) ensureKeyboardVisible();
}

function toggleKeyboard() {
  const vk = window.mathVirtualKeyboard;
  if (!vk) {
    focusMathfield(true);
    return;
  }
  try {
    vk.visible = !vk.visible;
    syncKeyboardState();
    syncLayout();
    if (vk.visible) mathfield?.focus();
  } catch (_) {
    focusMathfield(true);
  }
}

function installClipboardBridge() {
  if (!bridge) return;
  const clipboardApi = {
    async readText() {
      return new Promise((resolve, reject) => {
        try {
          if (typeof bridge.readClipboardText === 'function') {
            bridge.readClipboardText((text) => resolve(String(text ?? '')));
            return;
          }
          reject(new Error('剪贴板读取接口不可用'));
        } catch (err) {
          reject(err);
        }
      });
    },
    async writeText(text) {
      return new Promise((resolve, reject) => {
        try {
          if (typeof bridge.writeClipboardText === 'function') {
            bridge.writeClipboardText(String(text ?? ''), (ok) => {
              if (ok === false) {
                reject(new Error('剪贴板写入失败'));
              } else {
                resolve();
              }
            });
            return;
          }
          reject(new Error('剪贴板写入接口不可用'));
        } catch (err) {
          reject(err);
        }
      });
    },
  };
  try {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: clipboardApi,
    });
  } catch (_) {
    try {
      navigator.clipboard = clipboardApi;
    } catch (_) {
      // Ignore if the current engine does not allow overriding clipboard.
    }
  }
}

function setupBridge() {
  return new Promise((resolve) => {
    if (!window.qt || !window.QWebChannel) {
      resolve();
      return;
    }
    new QWebChannel(qt.webChannelTransport, (channel) => {
      bridge = channel.objects.pyBridge || null;
      resolve();
    });
  });
}

async function init() {
  await setupBridge();
  try {
    const { MathfieldElement } = await import('https://esm.run/mathlive');
    installClipboardBridge();
    MathfieldElement.fontsDirectory = 'https://cdn.jsdelivr.net/npm/mathlive/fonts';
    if (window.mathVirtualKeyboard) {
      window.mathVirtualKeyboard.container = document.body;
      window.mathVirtualKeyboard.addEventListener?.('geometrychange', () => {
        syncKeyboardState();
        syncLayout();
      });
      window.mathVirtualKeyboard.addEventListener?.('visibilitychange', () => {
        syncKeyboardState();
        syncLayout();
      });
    }
    mathfield = new MathfieldElement();
    mathfield.tabIndex = 0;
    mathfield.mathVirtualKeyboardPolicy = 'onfocus';
    mathfield.smartFence = true;
    mathfield.smartMode = false;
    mathfield.defaultMode = 'math';
    mathfield.style.overflowX = 'auto';
    mathfield.style.overflowY = 'auto';
    const host = document.getElementById('mathfield-host');
    host.appendChild(mathfield);
    mathfield.addEventListener('input', () => {
      syncKeyboardState();
      syncLayout();
    });
    mathfield.addEventListener('focusin', () => {
      queueMicrotask(() => {
        syncKeyboardState();
        syncLayout();
      });
    });
    mathfield.addEventListener('focusout', () => setTimeout(() => {
      syncKeyboardState();
      syncLayout();
    }, 0));
    syncKeyboardState();
    syncLayout();
    focusMathfield(false);
  } catch (error) {
    const host = document.getElementById('mathfield-host');
    host.textContent = `MathLive 初始化失败：${String(error)}`;
  }
}

window.mathliveBridgeApi = {
  setThemeMode,
  currentLatex,
  clearMathfield,
  focusMathfield,
  toggleKeyboard,
  syncLayout,
};

window.addEventListener('resize', () => {
  syncKeyboardState();
  syncLayout();
});

init();
