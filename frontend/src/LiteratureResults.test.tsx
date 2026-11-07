// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { LiteratureResults, readLiteraturePapers, type Paper } from './LiteratureResults'

const paper: Paper = {
  title: '医学影像论文', authors: ['Ada Lovelace'], publication_year: 2024,
  journal_or_venue: 'Imaging Journal', abstract: 'Study abstract.',
  doi: '10.1234/paper', url: 'https://doi.org/10.1234/paper', source: 'Crossref',
}

afterEach(() => vi.restoreAllMocks())

it('reads a structured list and distinguishes an empty list from missing output', () => {
  expect(readLiteraturePapers({ papers: [paper] })).toEqual([paper])
  expect(readLiteraturePapers({ papers: [] })).toEqual([])
  expect(readLiteraturePapers({ papers: [{ title: paper.title }] })).toBeNull()
  expect(readLiteraturePapers(null)).toBeNull()
})

it('renders bibliography, expandable abstracts, and original links and exports JSON', async () => {
  const createUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:literature-test')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  render(<LiteratureResults papers={[paper]} runId="run-123456789" title="结果输出" />)
  expect(screen.getByText('共 1 篇文献')).toBeInTheDocument()
  expect(screen.getByText(paper.title)).toBeInTheDocument()
  expect(screen.getByText(/Ada Lovelace.*2024.*Imaging Journal/)).toBeInTheDocument()
  expect(screen.getByText('Study abstract.').closest('details')).not.toHaveAttribute('open')
  expect(screen.getByRole('link', { name: '打开原文' })).toHaveAttribute('href', paper.url)
  fireEvent.click(screen.getByRole('button', { name: '导出 JSON' }))
  const exported = createUrl.mock.calls[0][0] as Blob
  const content = await new Promise<string>((resolve) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.readAsText(exported)
  })
  expect(JSON.parse(content)).toEqual([paper])
  expect(click.mock.contexts[0]).toHaveAttribute('download', 'literature-run-1234.json')
})

it('shows the empty state for a completed search with no records', () => {
  render(<LiteratureResults papers={[]} runId="empty" title="结果输出" />)
  expect(screen.getByText('共 0 篇文献')).toBeInTheDocument()
  expect(screen.getByText(/没有匹配文献/)).toBeInTheDocument()
})
