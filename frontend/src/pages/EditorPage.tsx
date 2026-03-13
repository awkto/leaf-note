import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import { api } from '../api'
import { Note, Tag } from '../types'
import { Save, ArrowLeft, Eye, Edit3, Pin, Globe, Download, Trash2 } from 'lucide-react'

export default function EditorPage({ onRefreshFolders }: { onRefreshFolders: () => void }) {
  const { id } = useParams()
  const navigate = useNavigate()
  const [note, setNote] = useState<Note | null>(null)
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')
  const [isPublic, setIsPublic] = useState(false)
  const [pinned, setPinned] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    if (id) {
      api.getNote(Number(id)).then(n => {
        setNote(n)
        setTitle(n.title)
        setContent(n.content)
        setTags(n.tags.map((t: Tag) => t.name))
        setIsPublic(n.is_public)
        setPinned(n.pinned)
      })
    }
  }, [id])

  const save = useCallback(async () => {
    setSaving(true)
    try {
      if (id) {
        await api.updateNote(Number(id), { title, content, tags, is_public: isPublic, pinned })
      } else {
        const n = await api.createNote({ title, content, tags, is_public: isPublic, pinned })
        navigate(`/note/${n.id}`, { replace: true })
      }
      setDirty(false)
      onRefreshFolders()
    } finally {
      setSaving(false)
    }
  }, [id, title, content, tags, isPublic, pinned, navigate, onRefreshFolders])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault()
        save()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [save])

  const handleTagAdd = () => {
    const t = tagInput.trim().toLowerCase()
    if (t && !tags.includes(t)) {
      setTags([...tags, t])
      setDirty(true)
    }
    setTagInput('')
  }

  const handleExport = async () => {
    if (!id) return
    const blob = await api.exportNote(Number(id))
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${note?.slug || 'note'}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleDelete = async () => {
    if (!id || !confirm('Delete this note?')) return
    await api.deleteNote(Number(id))
    onRefreshFolders()
    navigate('/')
  }

  return (
    <>
      <div className="editor-toolbar">
        <button className="btn-ghost" onClick={() => navigate('/')}>
          <ArrowLeft size={18} />
        </button>
        <input
          className="editor-title-input flex-1"
          value={title}
          onChange={e => { setTitle(e.target.value); setDirty(true) }}
          placeholder="Note title..."
        />
        <button
          className={`btn-ghost ${pinned ? 'pin-icon' : ''}`}
          onClick={() => { setPinned(!pinned); setDirty(true) }}
          title="Pin note"
        >
          <Pin size={16} />
        </button>
        <button
          className={`btn-ghost ${isPublic ? '' : 'text-muted'}`}
          onClick={() => { setIsPublic(!isPublic); setDirty(true) }}
          title={isPublic ? 'Public' : 'Private'}
        >
          <Globe size={16} />
        </button>
        <button className="btn-ghost" onClick={() => setShowPreview(!showPreview)}>
          {showPreview ? <Edit3 size={16} /> : <Eye size={16} />}
        </button>
        <button className="btn-ghost" onClick={handleExport} title="Export">
          <Download size={16} />
        </button>
        <button className="btn-ghost text-danger" onClick={handleDelete} title="Delete">
          <Trash2 size={16} />
        </button>
        <button className="btn-primary btn-sm" onClick={save} disabled={saving}>
          <Save size={14} /> {saving ? 'Saving...' : 'Save'}
        </button>
      </div>
      <div style={{ padding: '4px 16px', display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap' }}>
        {tags.map(t => (
          <span key={t} className="tag-badge" style={{ cursor: 'pointer' }}
            onClick={() => { setTags(tags.filter(x => x !== t)); setDirty(true) }}>
            {t} &times;
          </span>
        ))}
        <input
          style={{ width: 120, border: 'none', background: 'transparent', padding: '4px 0', fontSize: 12 }}
          placeholder="Add tag..."
          value={tagInput}
          onChange={e => setTagInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); handleTagAdd() } }}
          onBlur={handleTagAdd}
        />
      </div>
      <div className="editor-container">
        {!showPreview ? (
          <div className="editor-pane">
            <textarea
              className="editor-textarea"
              value={content}
              onChange={e => { setContent(e.target.value); setDirty(true) }}
              placeholder="Start writing in markdown..."
            />
          </div>
        ) : (
          <div className="preview-pane" style={{ flex: 1 }}>
            <div className="markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                {content}
              </ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
