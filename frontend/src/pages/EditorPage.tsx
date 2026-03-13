import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import { api } from '../api'
import { Note, Tag, FolderTree } from '../types'
import { Save, ArrowLeft, Eye, Edit3, Pin, Globe, Download, Trash2, Image } from 'lucide-react'

function insertAtCursor(
  textarea: HTMLTextAreaElement,
  content: string,
  currentContent: string,
  setContent: (s: string) => void,
) {
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const before = currentContent.substring(0, start)
  const after = currentContent.substring(end)
  const newContent = before + content + after
  setContent(newContent)
  // Restore cursor after React re-render
  requestAnimationFrame(() => {
    textarea.selectionStart = textarea.selectionEnd = start + content.length
    textarea.focus()
  })
}

function wrapSelection(
  textarea: HTMLTextAreaElement,
  prefix: string,
  suffix: string,
  currentContent: string,
  setContent: (s: string) => void,
) {
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const selected = currentContent.substring(start, end)
  const before = currentContent.substring(0, start)
  const after = currentContent.substring(end)
  const wrapped = prefix + (selected || 'text') + suffix
  setContent(before + wrapped + after)
  requestAnimationFrame(() => {
    if (selected) {
      textarea.selectionStart = start + prefix.length
      textarea.selectionEnd = end + prefix.length
    } else {
      textarea.selectionStart = start + prefix.length
      textarea.selectionEnd = start + prefix.length + 4 // select "text"
    }
    textarea.focus()
  })
}

function prefixLine(
  textarea: HTMLTextAreaElement,
  prefix: string,
  currentContent: string,
  setContent: (s: string) => void,
) {
  const start = textarea.selectionStart
  // Find start of current line
  const lineStart = currentContent.lastIndexOf('\n', start - 1) + 1
  const lineEnd = currentContent.indexOf('\n', start)
  const end = lineEnd === -1 ? currentContent.length : lineEnd
  const line = currentContent.substring(lineStart, end)
  // Remove existing heading prefixes
  const stripped = line.replace(/^#{1,6}\s*/, '')
  const newLine = prefix + stripped
  const before = currentContent.substring(0, lineStart)
  const after = currentContent.substring(end)
  setContent(before + newLine + after)
  requestAnimationFrame(() => {
    textarea.selectionStart = textarea.selectionEnd = lineStart + newLine.length
    textarea.focus()
  })
}

function findFolder(folders: FolderTree[], id: number): FolderTree | null {
  for (const f of folders) {
    if (f.id === id) return f
    const found = findFolder(f.children, id)
    if (found) return found
  }
  return null
}

function resolveDefaultView(
  noteView: string | null,
  folderId: number | null,
  folders: FolderTree[],
  globalDefault: string,
): boolean {
  // Note-level override
  if (noteView) return noteView === 'preview'
  // Walk up folder chain
  if (folderId) {
    let current = findFolder(folders, folderId)
    while (current) {
      if (current.default_view) return current.default_view === 'preview'
      current = current.parent_id ? findFolder(folders, current.parent_id) : null
    }
  }
  // Global default
  return globalDefault === 'preview'
}

export default function EditorPage({ onRefreshFolders, folders = [], globalDefaultView = 'source' }: {
  onRefreshFolders: () => void; folders?: FolderTree[]; globalDefaultView?: string
}) {
  const { id } = useParams()
  const navigate = useNavigate()
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
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
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    if (id) {
      api.getNote(Number(id)).then((n: Note) => {
        setNote(n)
        setTitle(n.title)
        setContent(n.content)
        setTags(n.tags.map((t: Tag) => t.name))
        setIsPublic(n.is_public)
        setPinned(n.pinned)
        setShowPreview(resolveDefaultView(n.default_view, n.folder_id, folders, globalDefaultView))
      })
    } else {
      setShowPreview(globalDefaultView === 'preview')
    }
  }, [id, folders, globalDefaultView])

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

  // Upload image and insert markdown at cursor
  const uploadAndInsert = useCallback(async (file: File) => {
    const textarea = textareaRef.current
    if (!textarea) return
    setUploading(true)
    const placeholder = `![Uploading ${file.name}...]()\n`
    insertAtCursor(textarea, placeholder, content, (c) => { setContent(c); setDirty(true) })
    try {
      const result = await api.uploadImage(file)
      setContent(prev => prev.replace(placeholder, `![${file.name}](${result.url})\n`))
      setDirty(true)
    } catch {
      setContent(prev => prev.replace(placeholder, ''))
    } finally {
      setUploading(false)
    }
  }, [content])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const ctrl = e.ctrlKey || e.metaKey
      const textarea = textareaRef.current

      // Ctrl+S: Save
      if (ctrl && e.key === 's') {
        e.preventDefault()
        save()
        return
      }

      if (!textarea || showPreview) return

      // Ctrl+Shift+1-6: Headings
      if (ctrl && e.shiftKey && e.key >= '1' && e.key <= '6') {
        e.preventDefault()
        const level = parseInt(e.key)
        prefixLine(textarea, '#'.repeat(level) + ' ', content, (c) => { setContent(c); setDirty(true) })
        return
      }

      // Ctrl+B: Bold
      if (ctrl && e.key === 'b') {
        e.preventDefault()
        wrapSelection(textarea, '**', '**', content, (c) => { setContent(c); setDirty(true) })
        return
      }

      // Ctrl+I: Italic
      if (ctrl && e.key === 'i') {
        e.preventDefault()
        wrapSelection(textarea, '*', '*', content, (c) => { setContent(c); setDirty(true) })
        return
      }

      // Ctrl+K: Link
      if (ctrl && e.key === 'k') {
        e.preventDefault()
        const start = textarea.selectionStart
        const end = textarea.selectionEnd
        const selected = content.substring(start, end)
        if (selected) {
          wrapSelection(textarea, '[', '](url)', content, (c) => { setContent(c); setDirty(true) })
        } else {
          insertAtCursor(textarea, '[text](url)', content, (c) => { setContent(c); setDirty(true) })
        }
        return
      }

      // Ctrl+Shift+K: Code block
      if (ctrl && e.shiftKey && e.key === 'K') {
        e.preventDefault()
        wrapSelection(textarea, '```\n', '\n```', content, (c) => { setContent(c); setDirty(true) })
        return
      }

      // Ctrl+`: Inline code
      if (ctrl && e.key === '`') {
        e.preventDefault()
        wrapSelection(textarea, '`', '`', content, (c) => { setContent(c); setDirty(true) })
        return
      }

      // Ctrl+E: Toggle preview
      if (ctrl && e.key === 'e') {
        e.preventDefault()
        setShowPreview(p => !p)
        return
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [save, content, showPreview])

  // Paste handler for images
  const handlePaste = useCallback(async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items
    if (!items) return
    for (const item of Array.from(items)) {
      if (item.type.startsWith('image/')) {
        e.preventDefault()
        const file = item.getAsFile()
        if (file) await uploadAndInsert(file)
        return
      }
    }
  }, [uploadAndInsert])

  // Drag and drop handler for images
  const handleDrop = useCallback(async (e: React.DragEvent<HTMLTextAreaElement>) => {
    const files = e.dataTransfer?.files
    if (!files) return
    for (const file of Array.from(files)) {
      if (file.type.startsWith('image/')) {
        e.preventDefault()
        await uploadAndInsert(file)
      }
    }
  }, [uploadAndInsert])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    if (e.dataTransfer?.types?.includes('Files')) {
      e.preventDefault()
    }
  }, [])

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

  const handleImageButton = () => fileInputRef.current?.click()

  const handleImageSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) await uploadAndInsert(file)
    if (fileInputRef.current) fileInputRef.current.value = ''
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
        <button className="btn-ghost" onClick={() => setShowPreview(!showPreview)} title="Toggle preview (Ctrl+E)">
          {showPreview ? <Edit3 size={16} /> : <Eye size={16} />}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          style={{ display: 'none' }}
          onChange={handleImageSelect}
        />
        <button className="btn-ghost" onClick={handleImageButton} title="Insert image" disabled={uploading}>
          <Image size={16} />
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
              ref={textareaRef}
              className="editor-textarea"
              value={content}
              onChange={e => { setContent(e.target.value); setDirty(true) }}
              onPaste={handlePaste}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
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
