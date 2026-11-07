export const literatureSearchComponentId = 'ict.paper.literature_search'
export const literatureResultComponentId = 'ict.paper.result_output'

export interface Paper {
  title: string
  authors: string[]
  publication_year: number | null
  journal_or_venue: string | null
  abstract: string | null
  doi: string | null
  url: string | null
  source: string
}

function isPaper(value: unknown): value is Paper {
  if (typeof value !== 'object' || value === null) return false
  const paper = value as Record<string, unknown>
  return typeof paper.title === 'string' && typeof paper.source === 'string' &&
    Array.isArray(paper.authors) && paper.authors.every((author) => typeof author === 'string') &&
    (paper.publication_year === null || Number.isInteger(paper.publication_year)) &&
    [paper.journal_or_venue, paper.abstract, paper.doi, paper.url].every((field) => field === null || typeof field === 'string')
}

export function readLiteraturePapers(output: Record<string, unknown> | null | undefined): Paper[] | null {
  const papers: unknown = output?.papers
  return Array.isArray(papers) && papers.every(isPaper) ? papers : null
}

function publicLink(url: string | null): string | undefined {
  if (!url) return undefined
  try {
    const parsed = new URL(url)
    if (['https:', 'http:'].includes(parsed.protocol) && !parsed.username && !parsed.password) return parsed.href
  } catch {
    return undefined
  }
}

function downloadPapers(papers: Paper[], runId: string) {
  // Export the same normalized records shown in the saved run, including missing fields.
  const url = URL.createObjectURL(new Blob([JSON.stringify(papers, null, 2)], { type: 'application/json;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `literature-${runId.slice(0, 8)}.json`
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function LiteratureResults({ papers, runId, title, query }: { papers: Paper[]; runId: string; title: string; query?: string }) {
  return <article className="workflow-run-report literature-results" aria-label="文献检索结果">
    <div className="workflow-run-report__heading">
      <div><span className="kicker">{title} · 本机运行记录</span><strong>共 {papers.length} 篇文献</strong></div>
      <button type="button" className="button secondary" onClick={() => downloadPapers(papers, runId)}>导出 JSON</button>
    </div>
    {query && <p>检索主题：{query}</p>}
    {papers.length === 0 ? <p role="status">没有匹配文献。可调整关键词或扩大年份范围后重新运行。</p> :
      <ol className="literature-results__papers">
        {papers.map((paper, index) => {
          const href = publicLink(paper.url)
          return <li key={`${index}-${paper.doi ?? paper.title}`}>
            <strong>{paper.title}</strong>
            <p>{paper.authors.join('、') || '未提供作者'} · {paper.publication_year ?? '未提供年份'} · {paper.journal_or_venue || '未提供期刊或会议'}</p>
            <div className="literature-results__links">
              <small>来源：{paper.source} · DOI：{paper.doi || '未提供'}</small>
              {href && <a href={href} target="_blank" rel="noopener noreferrer">打开原文</a>}
            </div>
            {paper.abstract ? <details><summary>摘要</summary><p>{paper.abstract}</p></details> : <small>数据源未提供摘要</small>}
          </li>
        })}
      </ol>}
  </article>
}
