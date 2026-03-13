import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import rehypeRaw from 'rehype-raw'
import { api } from '../api'
import { Note, Tag, FolderTree } from '../types'
import { Save, ArrowLeft, Eye, Edit3, Pin, Globe, Download, Trash2, Image, Columns, Check } from 'lucide-react'

type ViewMode = 'source' | 'preview' | 'split'

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
      textarea.selectionEnd = start + prefix.length + 4
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
  const lineStart = currentContent.lastIndexOf('\n', start - 1) + 1
  const lineEnd = currentContent.indexOf('\n', start)
  const end = lineEnd === -1 ? currentContent.length : lineEnd
  const line = currentContent.substring(lineStart, end)
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
): ViewMode {
  let resolved = globalDefault
  if (folderId) {
    let current = findFolder(folders, folderId)
    const chain: string[] = []
    while (current) {
      if (current.default_view) chain.unshift(current.default_view)
      current = current.parent_id ? findFolder(folders, current.parent_id) : null
    }
    if (chain.length > 0) resolved = chain[chain.length - 1]
  }
  if (noteView) resolved = noteView
  return resolved as ViewMode
}

function MarkdownPreview({ content }: { content: string }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw, rehypeHighlight]}>
        {content}
      </ReactMarkdown>
    </div>
  )
}

export default function EditorPage({ onRefreshFolders, folders = [], globalDefaultView = 'source' }: {
  onRefreshFolders: () => void; folders?: FolderTree[]; globalDefaultView?: string
}) {
  const { id } = useParams()
  const navigate = useNavigate()
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const autosaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [note, setNote] = useState<Note | null>(null)
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')
  const [isPublic, setIsPublic] = useState(false)
  const [pinned, setPinned] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('source')
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | 'unsaved' | ''>('')

  useEffect(() => {
    if (id) {
      api.getNote(Number(id)).then((n: Note) => {
        setNote(n)
        setTitle(n.title)
        setContent(n.content)
        setTags(n.tags.map((t: Tag) => t.name))
        setIsPublic(n.is_public)
        setPinned(n.pinned)
        setViewMode(resolveDefaultView(n.default_view, n.folder_id, folders, globalDefaultView))
        setSaveStatus('saved')
      })
    } else {
      setViewMode((globalDefaultView || 'source') as ViewMode)
    }
  }, [id])

  const save = useCallback(async () => {
    setSaving(true)
    setSaveStatus('saving')
    try {
      if (id) {
        await api.updateNote(Number(id), { title, content, tags, is_public: isPublic, pinned })
      } else {
        const n = await api.createNote({ title, content, tags, is_public: isPublic, pinned })
        navigate(`/note/${n.id}`, { replace: true })
      }
      setDirty(false)
      setSaveStatus('saved')
      onRefreshFolders()
    } catch {
      setSaveStatus('unsaved')
    } finally {
      setSaving(false)
    }
  }, [id, title, content, tags, isPublic, pinned, navigate, onRefreshFolders])

  // Autosave: debounce 1.5s after last change
  useEffect(() => {
    if (!dirty || !id) return
    if (autosaveTimer.current) clearTimeout(autosaveTimer.current)
    autosaveTimer.current = setTimeout(() => { save() }, 1500)
    return () => { if (autosaveTimer.current) clearTimeout(autosaveTimer.current) }
  }, [dirty, title, content, tags, isPublic, pinned])

  // Warn on browser close with unsaved changes
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirty) { e.preventDefault() }
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])

  const markDirty = useCallback(() => {
    setDirty(true)
    setSaveStatus('unsaved')
  }, [])

  // Upload image and insert markdown at cursor
  const uploadAndInsert = useCallback(async (file: File) => {
    const textarea = textareaRef.current
    if (!textarea) return
    setUploading(true)
    const placeholder = `![Uploading ${file.name}...]()\n`
    insertAtCursor(textarea, placeholder, content, (c) => { setContent(c); markDirty() })
    try {
      const result = await api.uploadImage(file)
      setContent(prev => prev.replace(placeholder, `![${file.name}](${result.url})\n`))
      markDirty()
    } catch {
      setContent(prev => prev.replace(placeholder, ''))
    } finally {
      setUploading(false)
    }
  }, [content, markDirty])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const ctrl = e.ctrlKey || e.metaKey
      const textarea = textareaRef.current

      if (ctrl && e.key === 's') {
        e.preventDefault()
        save()
        return
      }

      // Ctrl+E: cycle view modes
      if (ctrl && e.key === 'e') {
        e.preventDefault()
        setViewMode(m => m === 'source' ? 'preview' : m === 'preview' ? 'split' : 'source')
        return
      }

      // Ctrl+\: toggle split
      if (ctrl && e.key === '\\') {
        e.preventDefault()
        setViewMode(m => m === 'split' ? 'source' : 'split')
        return
      }

      if (!textarea || viewMode === 'preview') return

      if (ctrl && e.shiftKey && e.key >= '1' && e.key <= '6') {
        e.preventDefault()
        const level = parseInt(e.key)
        prefixLine(textarea, '#'.repeat(level) + ' ', content, (c) => { setContent(c); markDirty() })
        return
      }

      if (ctrl && e.key === 'b') {
        e.preventDefault()
        wrapSelection(textarea, '**', '**', content, (c) => { setContent(c); markDirty() })
        return
      }

      if (ctrl && e.key === 'i') {
        e.preventDefault()
        wrapSelection(textarea, '*', '*', content, (c) => { setContent(c); markDirty() })
        return
      }

      if (ctrl && e.key === 'k') {
        e.preventDefault()
        const start = textarea.selectionStart
        const end = textarea.selectionEnd
        const selected = content.substring(start, end)
        if (selected) {
          wrapSelection(textarea, '[', '](url)', content, (c) => { setContent(c); markDirty() })
        } else {
          insertAtCursor(textarea, '[text](url)', content, (c) => { setContent(c); markDirty() })
        }
        return
      }

      if (ctrl && e.shiftKey && e.key === 'K') {
        e.preventDefault()
        wrapSelection(textarea, '```\n', '\n```', content, (c) => { setContent(c); markDirty() })
        return
      }

      if (ctrl && e.key === '`') {
        e.preventDefault()
        wrapSelection(textarea, '`', '`', content, (c) => { setContent(c); markDirty() })
        return
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [save, content, viewMode, markDirty])

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
    if (e.dataTransfer?.types?.includes('Files')) e.preventDefault()
  }, [])

  const handleTagAdd = () => {
    const t = tagInput.trim().toLowerCase()
    if (t && !tags.includes(t)) {
      setTags([...tags, t])
      markDirty()
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

  const handleBack = () => {
    if (dirty && !confirm('You have unsaved changes. Discard?')) return
    navigate('/')
  }

  const editorPane = (
    <div className="editor-pane">
      <textarea
        ref={textareaRef}
        className="editor-textarea"
        value={content}
        onChange={e => { setContent(e.target.value); markDirty() }}
        onPaste={handlePaste}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        placeholder="Start writing in markdown..."
      />
    </div>
  )

  const previewPane = (
    <div className="preview-pane">
      <MarkdownPreview content={content} />
    </div>
  )

  return (
    <>
      <div className="editor-toolbar">
        <button className="btn-ghost" onClick={handleBack}>
          <ArrowLeft size={18} />
        </button>
        <input
          className="editor-title-input flex-1"
          value={title}
          onChange={e => { setTitle(e.target.value); markDirty() }}
          placeholder="Note title..."
        />
        {saveStatus && (
          <span className="save-status" data-status={saveStatus}>
            {saveStatus === 'saving' && 'Saving...'}
            {saveStatus === 'saved' && <><Check size={12} /> Saved</>}
            {saveStatus === 'unsaved' && 'Unsaved'}
          </span>
        )}
        <button
          className={`btn-ghost ${pinned ? 'pin-icon' : ''}`}
          onClick={() => { setPinned(!pinned); markDirty() }}
          title="Pin note"
        >
          <Pin size={16} />
        </button>
        <button
          className={`btn-ghost ${isPublic ? '' : 'text-muted'}`}
          onClick={() => { setIsPublic(!isPublic); markDirty() }}
          title={isPublic ? 'Public' : 'Private'}
        >
          <Globe size={16} />
        </button>
        <div className="view-toggle">
          <button
            className={`btn-ghost btn-sm ${viewMode === 'source' ? 'active' : ''}`}
            onClick={() => setViewMode('source')}
            title="Source (Ctrl+E)"
          >
            <Edit3 size={14} />
          </button>
          <button
            className={`btn-ghost btn-sm ${viewMode === 'split' ? 'active' : ''}`}
            onClick={() => setViewMode('split')}
            title="Split view (Ctrl+\)"
          >
            <Columns size={14} />
          </button>
          <button
            className={`btn-ghost btn-sm ${viewMode === 'preview' ? 'active' : ''}`}
            onClick={() => setViewMode('preview')}
            title="Preview (Ctrl+E)"
          >
            <Eye size={14} />
          </button>
        </div>
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
          <Save size={14} /> Save
        </button>
      </div>
      <div style={{ padding: '4px 16px', display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap' }}>
        {tags.map(t => (
          <span key={t} className="tag-badge" style={{ cursor: 'pointer' }}
            onClick={() => { setTags(tags.filter(x => x !== t)); markDirty() }}>
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
        {viewMode === 'source' && editorPane}
        {viewMode === 'preview' && previewPane}
        {viewMode === 'split' && (
          <>
            {editorPane}
            {previewPane}
          </>
        )}
      </div>
    </>
  )
}
