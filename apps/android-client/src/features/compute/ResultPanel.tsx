interface ResultPanelProps {
  title: string;
  summary: string;
  content: string;
  emptyText: string;
  tone?: 'default' | 'success' | 'danger';
}

export function ResultPanel({
  title,
  summary,
  content,
  emptyText,
  tone = 'default',
}: ResultPanelProps) {
  return (
    <section className={`card card--result card--${tone}`}>
      <div className="section-heading">
        <div>
          <p className="section-heading__eyebrow">{title}</p>
          <h2 className="section-heading__title">{summary}</h2>
        </div>
      </div>
      <pre className="result-block">{content || emptyText}</pre>
    </section>
  );
}