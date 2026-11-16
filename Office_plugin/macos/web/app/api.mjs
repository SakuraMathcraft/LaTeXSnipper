// Same-origin calls to the add-in host (LaTeXSnipper Office.app). The marker header makes
// every request a non-simple CORS request, which the server never preflights.
export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export const DESKTOP_OFFLINE = '无法连接到 LaTeXSnipper Office 插件服务，请打开“LaTeXSnipper Office”应用并点击“安装 / 修复”。';

export async function api(path, {method = 'GET', body, signal} = {}) {
  let response;
  try {
    response = await fetch(path, {
      method,
      signal,
      cache: 'no-store',
      headers: {'X-LaTeXSnipper-Office': '1', ...(body === undefined ? {} : {'Content-Type': 'application/json'})},
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (error?.name === 'AbortError') throw error;
    throw new ApiError(0, 'host_offline', DESKTOP_OFFLINE);
  }
  let payload = null;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    const error = payload?.error || {};
    throw new ApiError(response.status, error.code || 'request_failed', error.message || `LaTeXSnipper 请求失败（${response.status}）。`);
  }
  return payload;
}

let catalogPromise = null;
export function catalog() {
  catalogPromise ||= api('/api/catalog').catch(error => { catalogPromise = null; throw error; });
  return catalogPromise;
}

export function loadSettings(host) {
  return api(`/api/settings/${host}`);
}
