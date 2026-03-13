import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { NoteSummary } from '../types'
import { Search, FileText, Pin } from 'lucide-react'

export default function SearchPage() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<NoteSummary[]>([])
  const [total, setTotal] = useState(0)
  const [searched, setSearched] = useState(false)

  const handleSearch = async () => {
    if (!query.trim()) return
    const res = await api.search(query)
    setResults(res.notes)
    setTotal(res.total)
    setSearched(true)
  }

  const formatDate = (d: string) =>
    new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })

  return (
    <>
      <div className="page-header">
        <h1>Search</h1>
      </div>
      <div className="page-body">
        <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
          <div className="search-bar" style={{ maxWidth: 'none' }}>
            <Search size={16} />
            <input
              placeholder="Search notes by title or content..."
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
            />
          </div>
          <button className="btn-primary" onClick={handleSearch}>Search</button>
        </div>

        {searched && (
          <p className="text-sm text-muted mb-2">{total} result{total !== 1 ? 's' : ''} found</p>
        )}

        <div className="note-list">
          {results.map(note => (
            <div key={note.id} className="note-item" onClick={() => navigate(`/note/${note.id}`)}>
              {note.pinned && <Pin size={14} className="pin-icon" />}
              <span className="title">{note.title}</span>
              <div className="tags-row">
                {note.tags.map(t => (
                  <span key={t.id} className="tag-badge" style={{ borderLeft: `3px solid ${t.color}` }}>
                    {t.name}
                  </span>
                ))}
              </div>
              <span className="meta">{formatDate(note.updated_at)}</span>
            </div>
          ))}
        </div>

        {searched && results.length === 0 && (
          <div className="empty-state">
            <FileText />
            <p>No notes match your search</p>
          </div>
        )}
      </div>
    </>
  )
}
