export type ComputeAction =
  | 'evaluate'
  | 'simplify'
  | 'numeric'
  | 'expand'
  | 'factor'
  | 'solve';

export type LayoutKind = 'displaylines' | 'align' | 'multline';

export interface WorkbenchSnippet {
  id: string;
  label: string;
  latex: string;
  description: string;
}

export interface WorkbenchSample {
  id: string;
  label: string;
  latex: string;
  note: string;
}

export interface WorkbenchResult {
  action: ComputeAction;
  ok: boolean;
  summary: string;
  latex: string;
  text: string;
  mathJson: string;
}

export interface WorkbenchHistoryItem {
  id: string;
  latex: string;
  summary: string;
  createdAt: string;
}

export interface ImportedTextFile {
  name: string;
  mimeType: string;
  size: number;
  text: string;
}

export interface MathEditorHandle {
  focus: () => void;
  getLatex: () => string;
  setLatex: (value: string) => void;
  insertLatex: (value: string) => void;
  applyLayout: (kind: LayoutKind) => void;
}