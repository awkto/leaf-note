import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { NoteSummary } from '../types'
import { Plus, FileText, Pin, Download, Upload, Trash2 } from 'lucide-react'

export default function NotesPage({ folderId, onRefreshFolders }: {
  folderId: number | null; onRefreshFolders: () => void
}) {
  const navigate = useNavigate()
  const [notes, setNotes] = useState<NoteSummary[]>([])
  const [loading, setLoading] = useState(true)
  const fileInputRef = useState<HTMLInputElement | null>(null)

  useEffect(() => { loadNotes() }, [folderId])

  const loadNotes = () => {
    setLoading(true)
    const params: Record<string, string> = {}
    if (folderId !== null) params.folder_id = String(folderId)
    api.listNotes(params).then(setNotes).catch(() => {}).finally(() => setLoading(false))
  }

  const handleNew = async () => {
    const note = await api.createNote({
      title: 'Untitled',
      content: '',
      folder_id: folderId,
      tags: [],
    })
    onRefreshFolders()
    navigate(`/note/${note.id}`)
  }

  const handleDelete = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation()
    if (!confirm('Delete this note?')) return
    await api.deleteNote(id)
    onRefreshFolders()
    loadNotes()
  }

  const handleExportAll = async () => {
    const blob = await api.exportAll()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'leaf-notes-export.zip'
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files?.length) return
    await api.importMarkdown(e.target.files, folderId ?? undefined)
    loadNotes()
    onRefreshFolders()
  }

  const formatDate = (d: string) => {
    const date = new Date(d)
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  }

  return (
    <>
      <div className="page-header">
        <h1>{folderId ? 'Folder Notes' : 'All Notes'}</h1>
        <div className="flex gap-2">
          <input
            type="file"
            accept=".md,.zip"
            multiple
            style={{ display: 'none' }}
            id="import-input"
            onChange={handleImport}
          />
          <button className="btn-secondary btn-sm" onClick={() => document.getElementById('import-input')?.click()}>
            <Upload size={14} /> Import
          </button>
          <button className="btn-secondary btn-sm" onClick={handleExportAll}>
            <Download size={14} /> Export All
          </button>
          <button className="btn-primary" onClick={handleNew}>
            <Plus size={16} /> New Note
          </button>
        </div>
      </div>
      <div className="page-body">
        {loading ? (
          <div className="empty-state"><p>Loading...</p></div>
        ) : notes.length === 0 ? (
          <div className="empty-state">
            <FileText />
            <p>No notes yet</p>
            <button className="btn-primary" onClick={handleNew}>Create your first note</button>
          </div>
        ) : (
          <div className="note-list">
            {notes.map(note => (
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
                <span className="meta">
                  {note.is_public && <span className="tag-badge">public</span>}
                  {formatDate(note.updated_at)}
                </span>
                <button className="btn-ghost btn-sm" onClick={(e) => handleDelete(e, note.id)}>
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
