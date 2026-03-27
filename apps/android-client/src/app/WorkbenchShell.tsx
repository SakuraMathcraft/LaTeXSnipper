import { startTransition, useEffect, useRef, useState } from 'react';

import { ResultPanel } from '../features/compute/ResultPanel';
import { MathEditor } from '../features/editor/MathEditor';
import {
  copyText,
  importTextFile,
  isNativePlatform,
  loadPersistedWorkbenchState,
  persistWorkbenchState,
  shareText,
} from '../services/native';
import {
  computeActions,
  getMathJsonPreview,
  runComputeAction,
  samples,
  snippets,
  warmupWorkbenchEngine,
} from '../services/workbench';
import type {
  ComputeAction,
  LayoutKind,
  MathEditorHandle,
  WorkbenchHistoryItem,
  WorkbenchResult,
} from '../types/workbench';

const initialLatex = '\\int_0^{\\pi} \\sin(x)\\,dx';

const emptyResult: WorkbenchResult = {
  action: 'evaluate',
  ok: true,
  summary: '等待执行计算',
  latex: '',
  text: '',
  mathJson: 'null',
};

export function WorkbenchShell() {
  const editorRef = useRef<MathEditorHandle | null>(null);
  const previewTaskRef = useRef(0);
  const [latex, setLatex] = useState(initialLatex);
  const [mathJson, setMathJson] = useState('正在加载计算引擎...');
  const [status, setStatus] = useState('正在初始化移动端数学工作台...');
  const [result, setResult] = useState<WorkbenchResult>(emptyResult);
  const [history, setHistory] = useState<WorkbenchHistoryItem[]>([]);
  const [editorReady, setEditorReady] = useState(false);
  const [engineReady, setEngineReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [bootstrapped, setBootstrapped] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      try {
        const persisted = await loadPersistedWorkbenchState();
        if (cancelled) return;

        startTransition(() => {
          setLatex(persisted.draftLatex || initialLatex);
          setHistory(persisted.history || []);
          setStatus('移动端工作台已恢复上次草稿。');
          setBootstrapped(true);
        });
      } catch {
        if (!cancelled) {
          setBootstrapped(true);
          setStatus('移动端工作台已启动。');
        }
      }
    };

    void bootstrap();
    void warmupWorkbenchEngine().then(() => {
      if (!cancelled) setEngineReady(true);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!bootstrapped) return;

    const timeoutId = window.setTimeout(() => {
      void persistWorkbenchState({ draftLatex: latex, history });
    }, 180);

    return () => window.clearTimeout(timeoutId);
  }, [bootstrapped, history, latex]);

  useEffect(() => {
    let cancelled = false;
    const taskId = ++previewTaskRef.current;

    setMathJson(engineReady ? '正在解析表达式...' : '正在加载计算引擎...');

    const refresh = async () => {
      const preview = await getMathJsonPreview(latex);
      if (cancelled || taskId !== previewTaskRef.current) return;
      setMathJson(preview);
      setEngineReady(true);
    };

    void refresh();

    return () => {
      cancelled = true;
    };
  }, [engineReady, latex]);

  const syncLatex = (nextValue: string) => {
    startTransition(() => setLatex(nextValue));
  };

  const handleRun = async (action: ComputeAction) => {
    setBusy(true);
    setStatus(`${computeActions.find((item) => item.id === action)?.label ?? '计算'}处理中...`);

    try {
      const next = await runComputeAction(action, latex);
      setResult(next);
      setStatus(next.ok ? next.summary : next.text);
      if (next.ok) {
        setHistory((current) => buildHistory(next, latex, current));
      }
    } finally {
      setBusy(false);
    }
  };

  const handleUseSample = (sampleLatex: string) => {
    editorRef.current?.setLatex(sampleLatex);
    setStatus('已载入示例公式。');
  };

  const handleInsert = (snippetLatex: string) => {
    editorRef.current?.insertLatex(snippetLatex);
    setStatus('已插入快捷模板。');
  };

  const handleApplyLayout = (kind: LayoutKind) => {
    editorRef.current?.applyLayout(kind);
    setStatus(`已切换为 ${kind} 多行排版。`);
  };

  const handleClear = () => {
    editorRef.current?.setLatex('');
    setResult(emptyResult);
    setStatus('编辑区已清空。');
  };

  const handleCopy = async (value: string, label: string) => {
    try {
      await copyText(value, `LaTeXSnipper ${label}`);
      setStatus(`${label}已复制到剪贴板。`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : `复制${label}失败`);
    }
  };

  const handleShare = async () => {
    const payload = result.ok && result.latex ? `输入:\n${latex}\n\n结果:\n${result.latex}` : latex;

    try {
      await shareText({ title: 'LaTeXSnipper 数学工作台', text: payload });
      setStatus('已打开系统分享面板。');
    } catch (error) {
      setStatus(error instanceof Error ? error.message : '系统分享失败');
    }
  };

  const handleImport = async () => {
    try {
      const imported = await importTextFile();
      if (!imported) {
        setStatus('已取消文件导入。');
        return;
      }

      editorRef.current?.setLatex(imported.text);
      setStatus(`已导入 ${imported.name}。`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : '文件导入失败');
    }
  };

  const handleRestoreHistory = (entry: WorkbenchHistoryItem) => {
    editorRef.current?.setLatex(entry.latex);
    setStatus(`已恢复 ${formatTimestamp(entry.createdAt)} 的记录。`);
  };

  const nativeLabel = isNativePlatform() ? 'Capacitor Native' : 'Web Fallback';
  const readyLabel = editorReady && engineReady ? 'Ready' : 'Loading';

  return (
    <div className="shell">
      <header className="hero">
        <div className="hero__copy">
          <p className="hero__eyebrow">LaTeXSnipper / Android Client</p>
          <h1 className="hero__title">数学工作台移动端</h1>
          <p className="hero__subtitle">
            MathLive 和 Compute Engine 已改成按需加载，同时补上 Capacitor 原生剪贴板、分享、文件导入与历史持久化。
          </p>
        </div>
        <div className="hero__status-row">
          <div className="hero__status">
            <span className="hero__status-dot" />
            <span>{status}</span>
          </div>
          <div className="badge-row">
            <span className="status-badge">{readyLabel}</span>
            <span className="status-badge status-badge--muted">{nativeLabel}</span>
          </div>
        </div>
      </header>

      <main className="workspace">
        <section className="card card--editor">
          <div className="section-heading">
            <div>
              <p className="section-heading__eyebrow">Editor</p>
              <h2 className="section-heading__title">公式输入区</h2>
            </div>
            <div className="toolbar-row">
              <button type="button" className="ghost-button" onClick={handleImport} disabled={busy}>
                导入文件
              </button>
              <button type="button" className="ghost-button" onClick={() => handleCopy(latex, 'LaTeX')} disabled={busy}>
                复制 LaTeX
              </button>
              <button type="button" className="ghost-button" onClick={handleShare} disabled={busy}>
                系统分享
              </button>
              <button type="button" className="ghost-button" onClick={handleClear} disabled={busy}>
                清空
              </button>
            </div>
          </div>

          <MathEditor ref={editorRef} value={latex} onChange={syncLatex} onReadyChange={setEditorReady} />

          <div className="chip-group">
            {computeActions.map((item) => (
              <button
                key={item.id}
                type="button"
                className="chip chip--action"
                onClick={() => void handleRun(item.id)}
                title={item.note}
                disabled={busy || !editorReady}
              >
                {busy ? '处理中...' : item.label}
              </button>
            ))}
          </div>

          <div className="action-grid">
            <div className="subsection">
              <div className="subsection__header">
                <h3>快捷模板</h3>
                <span>沿用桌面端常用模板</span>
              </div>
              <div className="chip-group">
                {snippets.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="chip"
                    onClick={() => handleInsert(item.latex)}
                    title={item.description}
                    disabled={!editorReady}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="subsection">
              <div className="subsection__header">
                <h3>多行排版</h3>
                <span>适配手机上的推导书写</span>
              </div>
              <div className="chip-group">
                <button type="button" className="chip" onClick={() => handleApplyLayout('displaylines')} disabled={!editorReady}>
                  displaylines
                </button>
                <button type="button" className="chip" onClick={() => handleApplyLayout('align')} disabled={!editorReady}>
                  align
                </button>
                <button type="button" className="chip" onClick={() => handleApplyLayout('multline')} disabled={!editorReady}>
                  multline
                </button>
              </div>
            </div>

            <div className="subsection">
              <div className="subsection__header">
                <h3>示例公式</h3>
                <span>用于快速验证移动端交互</span>
              </div>
              <div className="sample-list">
                {samples.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="sample-card"
                    onClick={() => handleUseSample(item.latex)}
                  >
                    <strong>{item.label}</strong>
                    <span>{item.note}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </section>

        <aside className="sidebar">
          <ResultPanel
            title="Result"
            summary={result.summary}
            content={result.ok ? result.latex : result.text}
            emptyText="执行计算后，结果会显示在这里。"
            tone={result.ok ? 'success' : 'danger'}
          />

          <ResultPanel
            title="MathJSON"
            summary={engineReady ? '结构化表达式' : '引擎正在按需加载'}
            content={mathJson}
            emptyText="等待输入公式..."
          />

          <section className="card">
            <div className="section-heading">
              <div>
                <p className="section-heading__eyebrow">History</p>
                <h2 className="section-heading__title">最近记录</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => handleCopy(mathJson, 'MathJSON')}>
                复制 MathJSON
              </button>
            </div>
            <div className="history-list">
              {history.length ? (
                history.map((entry) => (
                  <button
                    key={entry.id}
                    type="button"
                    className="history-card"
                    onClick={() => handleRestoreHistory(entry)}
                  >
                    <strong>{entry.summary}</strong>
                    <span>{entry.latex}</span>
                    <small>{formatTimestamp(entry.createdAt)}</small>
                  </button>
                ))
              ) : (
                <p className="empty-note">暂时还没有历史记录。</p>
              )}
            </div>
          </section>
        </aside>
      </main>
    </div>
  );
}

function buildHistory(
  result: WorkbenchResult,
  latex: string,
  current: WorkbenchHistoryItem[],
): WorkbenchHistoryItem[] {
  const item: WorkbenchHistoryItem = {
    id: `${Date.now()}`,
    latex,
    summary: result.summary,
    createdAt: new Date().toISOString(),
  };

  return [item, ...current].slice(0, 12);
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}