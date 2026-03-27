import { Capacitor } from '@capacitor/core';

import type { ImportedTextFile, WorkbenchHistoryItem } from '../types/workbench';

const DRAFT_KEY = 'workbench:draft';
const HISTORY_KEY = 'workbench:history';
const HISTORY_LIMIT = 12;

interface PersistedWorkbenchState {
  draftLatex: string;
  history: WorkbenchHistoryItem[];
}

export function isNativePlatform(): boolean {
  return Capacitor.isNativePlatform();
}

export async function copyText(value: string, label = 'LaTeXSnipper'): Promise<void> {
  if (!value.trim()) {
    throw new Error('没有可复制的内容');
  }

  try {
    const { Clipboard } = await import('@capacitor/clipboard');
    await Clipboard.write({ string: value, label });
    return;
  } catch {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }
  }

  throw new Error('当前环境不支持剪贴板写入');
}

export async function shareText(options: { title: string; text: string }): Promise<void> {
  const payload = options.text.trim();
  if (!payload) {
    throw new Error('没有可分享的内容');
  }

  try {
    const { Share } = await import('@capacitor/share');
    const capability = await Share.canShare();
    if (capability.value) {
      await Share.share({
        title: options.title,
        text: payload,
        dialogTitle: options.title,
      });
      return;
    }
  } catch {
    // fall through to web share
  }

  if (navigator.share) {
    await navigator.share({ title: options.title, text: payload });
    return;
  }

  throw new Error('当前环境不支持系统分享');
}

export async function importTextFile(): Promise<ImportedTextFile | null> {
  if (isNativePlatform()) {
    const { FilePicker } = await import('@capawesome/capacitor-file-picker');
    const result = await FilePicker.pickFiles({
      limit: 1,
      readData: true,
      types: ['text/plain', 'application/json', 'application/x-tex', 'text/x-tex'],
    });

    const picked = result.files[0];
    if (!picked) return null;

    const text = await readPickedFileText(picked);
    return {
      name: picked.name,
      mimeType: picked.mimeType,
      size: picked.size,
      text,
    };
  }

  return pickTextFileFromBrowser();
}

export async function loadPersistedWorkbenchState(): Promise<PersistedWorkbenchState> {
  const draftLatex = (await readPreference(DRAFT_KEY)) ?? '';
  const historyRaw = (await readPreference(HISTORY_KEY)) ?? '[]';

  try {
    const parsed = JSON.parse(historyRaw) as WorkbenchHistoryItem[];
    return {
      draftLatex,
      history: Array.isArray(parsed) ? parsed.slice(0, HISTORY_LIMIT) : [],
    };
  } catch {
    return { draftLatex, history: [] };
  }
}

export async function persistWorkbenchState(state: PersistedWorkbenchState): Promise<void> {
  await writePreference(DRAFT_KEY, state.draftLatex);
  await writePreference(HISTORY_KEY, JSON.stringify(state.history.slice(0, HISTORY_LIMIT)));
}

async function readPreference(key: string): Promise<string | null> {
  try {
    const { Preferences } = await import('@capacitor/preferences');
    await Preferences.configure({ group: 'LaTeXSnipperWorkbench' });
    const result = await Preferences.get({ key });
    return result.value;
  } catch {
    return localStorage.getItem(key);
  }
}

async function writePreference(key: string, value: string): Promise<void> {
  try {
    const { Preferences } = await import('@capacitor/preferences');
    await Preferences.configure({ group: 'LaTeXSnipperWorkbench' });
    await Preferences.set({ key, value });
    return;
  } catch {
    localStorage.setItem(key, value);
  }
}

async function readPickedFileText(file: { blob?: Blob; data?: string; path?: string }): Promise<string> {
  if (file.blob) {
    return file.blob.text();
  }

  if (file.data) {
    return decodeBase64ToUtf8(file.data);
  }

  if (file.path) {
    const response = await fetch(file.path);
    return response.text();
  }

  throw new Error('无法读取所选文件内容');
}

function decodeBase64ToUtf8(value: string): string {
  const binary = atob(value);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function pickTextFileFromBrowser(): Promise<ImportedTextFile | null> {
  return new Promise((resolve, reject) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.tex,.txt,.json,text/plain,application/json';
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) {
        resolve(null);
        return;
      }

      try {
        const text = await file.text();
        resolve({
          name: file.name,
          mimeType: file.type || 'text/plain',
          size: file.size,
          text,
        });
      } catch (error) {
        reject(error);
      }
    };
    input.click();
  });
}