import { useState, useEffect, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { api } from '../api'
import { NoteSummary, Folder } from '../types'
import { Plus, FileText, Pin, Download, Upload, Trash2 } from 'lucide-react'

export default function NotesPage({ onRefreshFolders }: {
  onRefreshFolders: () => void
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const [notes, setNotes] = useState<NoteSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [folder, setFolder] = useState<Folder | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  // Extract folder path from URL: /notes/infrastructure/docker → infrastructure/docker
  const folderPath = location.pathname.startsWith('/notes/')
    ? decodeURIComponent(location.pathname.slice(7))
    : null

  useEffect(() => {
    setLoading(true)
    setFolder(null)

    if (folderPath) {
      // Path-based: fetch folder info and notes via path
      Promise.all([
        api.getFolderByPath(folderPath).catch(() => null),
        api.browseByPath(folderPath).catch(() => []),
      ]).then(([f, n]) => {
        setFolder(f)
        setNotes(Array.isArray(n) ? n : [])
      }).finally(() => setLoading(false))
    } else {
      // Root: all notes
      api.listNotes().then(setNotes).catch(() => {}).finally(() => setLoading(false))
    }
  }, [folderPath])

  const handleNew = async () => {
    const data: any = { title: 'Untitled', content: '', tags: [] }
    if (folder) {
      data.folder_id = folder.id
    }
    const note = await api.createNote(data)
    onRefreshFolders()
    navigate(`/note/${note.id}`)
  }

  const handleDelete = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation()
    if (!confirm('Delete this note?')) return
    await api.deleteNote(id)
    onRefreshFolders()
    // Reload
    if (folderPath) {
      api.browseByPath(folderPath).then(n => setNotes(Array.isArray(n) ? n : []))
    } else {
      api.listNotes().then(setNotes)
    }
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
    await api.importMarkdown(e.target.files, folder?.id)
    if (folderPath) {
      api.browseByPath(folderPath).then(n => setNotes(Array.isArray(n) ? n : []))
    } else {
      api.listNotes().then(setNotes)
    }
    onRefreshFolders()
  }

  const formatDate = (d: string) => {
    const date = new Date(d)
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  }

  const title = folderPath
    ? folderPath.split('/').pop() || 'Notes'
    : 'All Notes'

  return (
    <>
      <div className="page-header">
        <div>
          <h1>{title}</h1>
          {folderPath && (
            <div className="text-sm text-muted" style={{ marginTop: 2 }}>
              {folderPath}
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".md,.zip"
            multiple
            style={{ display: 'none' }}
            onChange={handleImport}
          />
          <button className="btn-secondary btn-sm" onClick={() => fileInputRef.current?.click()}>
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
                {note.excerpt && <span className="note-excerpt">{note.excerpt}</span>}
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
