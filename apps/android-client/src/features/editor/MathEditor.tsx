import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import type { MathfieldElement } from 'mathlive';

import { applyMultilineLayout } from '../../services/workbench';
import type { LayoutKind, MathEditorHandle } from '../../types/workbench';

interface MathEditorProps {
  value: string;
  onChange: (value: string) => void;
  onReadyChange?: (ready: boolean) => void;
}

export const MathEditor = forwardRef<MathEditorHandle, MathEditorProps>(function MathEditor(
  { value, onChange, onReadyChange },
  ref,
) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const fieldRef = useRef<MathfieldElement | null>(null);

  useEffect(() => {
    let disposed = false;
    let removeListener: (() => void) | null = null;

    const mount = async () => {
      if (!hostRef.current) return;

      const { MathfieldElement } = await import('mathlive');
      if (disposed || !hostRef.current) return;

      const field = new MathfieldElement();
      fieldRef.current = field;
      field.value = value;
      field.smartFence = true;
      field.smartMode = false;
      field.inlineShortcuts = { pi: '\\pi', sqrt: '\\sqrt{#0}' };
      field.mathVirtualKeyboardPolicy = 'auto';
      field.letterShapeStyle = 'tex';
      field.className = 'math-editor__field';

      const syncValue = () => onChange(field.getValue('latex-expanded'));
      field.addEventListener('input', syncValue);
      removeListener = () => field.removeEventListener('input', syncValue);
      hostRef.current.appendChild(field);
      onReadyChange?.(true);
    };

    onReadyChange?.(false);
    void mount();

    return () => {
      disposed = true;
      removeListener?.();
      fieldRef.current?.remove();
      fieldRef.current = null;
      onReadyChange?.(false);
    };
  }, [onChange, onReadyChange]);

  useEffect(() => {
    const field = fieldRef.current;
    if (!field) return;

    const current = field.getValue('latex-expanded');
    if (current !== value) {
      field.setValue(value, { silenceNotifications: true });
    }
  }, [value]);

  useImperativeHandle(ref, () => ({
    focus: () => fieldRef.current?.focus(),
    getLatex: () => fieldRef.current?.getValue('latex-expanded') ?? '',
    setLatex: (nextValue: string) => {
      const field = fieldRef.current;
      if (!field) return;
      field.setValue(nextValue, { silenceNotifications: true });
      onChange(field.getValue('latex-expanded'));
    },
    insertLatex: (snippet: string) => {
      const field = fieldRef.current;
      if (!field) return;
      field.insert(snippet, { format: 'latex' });
      onChange(field.getValue('latex-expanded'));
      field.focus();
    },
    applyLayout: (kind: LayoutKind) => {
      const field = fieldRef.current;
      if (!field) return;
      const nextValue = applyMultilineLayout(field.getValue('latex-expanded'), kind);
      field.setValue(nextValue, { silenceNotifications: true });
      onChange(field.getValue('latex-expanded'));
      field.focus();
    },
  }), [onChange]);

  return <div ref={hostRef} className="math-editor" />;
});