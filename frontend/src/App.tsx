import { Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom'
import { useState, useEffect, useCallback } from 'react'
import { api } from './api'
import { FolderTree, FolderNoteRef, NoteSummary, Settings as SettingsType } from './types'
import NotesPage from './pages/NotesPage'
import EditorPage from './pages/EditorPage'
import SearchPage from './pages/SearchPage'
import SettingsPage from './pages/SettingsPage'
import LoginPage from './pages/LoginPage'
import {
  FileText, Search, Settings, FolderOpen, ChevronRight, ChevronDown,
  Plus, Leaf, Pin, Home, Lock, Unlock
} from 'lucide-react'

function NoteItem({ note, active, editMode, onDragStart }: {
  note: FolderNoteRef | NoteSummary; active: boolean;
  editMode: boolean; onDragStart?: (e: React.DragEvent, noteId: number) => void
}) {
  const navigate = useNavigate()
  return (
    <div
      className={`sidebar-note ${active ? 'active' : ''} ${editMode ? 'draggable' : ''}`}
      onClick={() => navigate(`/note/${note.id}`)}
      draggable={editMode}
      onDragStart={editMode ? (e) => onDragStart?.(e, note.id) : undefined}
    >
      {note.pinned && <Pin size={10} className="pin-icon" />}
      <span>{note.title}</span>
    </div>
  )
}

function FolderTreeItem({ folder, depth = 0, pathPrefix = '', activePath, activeNoteId, onSelect, editMode, onDragStart, onDrop }: {
  folder: FolderTree; depth?: number; pathPrefix?: string;
  activePath: string; activeNoteId: number | null; onSelect: (path: string) => void;
  editMode: boolean; onDragStart: (e: React.DragEvent, noteId: number) => void;
  onDrop: (noteId: number, folderId: number | null) => void
}) {
  const [open, setOpen] = useState(true)
  const [dragOver, setDragOver] = useState(false)
  const hasChildren = folder.children.length > 0 || folder.notes.length > 0
  const folderPath = pathPrefix ? `${pathPrefix}/${folder.slug}` : folder.slug

  const handleDragOver = (e: React.DragEvent) => {
    if (!editMode) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOver(true)
  }

  const handleDragLeave = () => setDragOver(false)

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const noteId = Number(e.dataTransfer.getData('text/plain'))
    if (noteId) onDrop(noteId, folder.id)
  }

  return (
    <div>
      <div
        className={`folder-item ${activePath === folderPath ? 'active' : ''} ${dragOver ? 'drag-over' : ''}`}
        style={{ paddingLeft: 12 + depth * 16 }}
        onClick={() => onSelect(folderPath)}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {hasChildren ? (
          <span onClick={(e) => { e.stopPropagation(); setOpen(!open) }}>
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        ) : <span style={{ width: 14 }} />}
        <FolderOpen size={14} />
        <span style={{ flex: 1 }}>{folder.name}</span>
        <span className="count">{folder.note_count}</span>
      </div>
      {hasChildren && open && (
        <div className="folder-children">
          {folder.children.map(c => (
            <FolderTreeItem key={c.id} folder={c} depth={depth + 1}
              pathPrefix={folderPath} activePath={activePath} activeNoteId={activeNoteId}
              onSelect={onSelect} editMode={editMode} onDragStart={onDragStart} onDrop={onDrop} />
          ))}
          {folder.notes.map(n => (
            <NoteItem key={n.id} note={n} active={activeNoteId === n.id}
              editMode={editMode} onDragStart={onDragStart} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const [folders, setFolders] = useState<FolderTree[]>([])
  const [rootNotes, setRootNotes] = useState<NoteSummary[]>([])
  const [showNewFolder, setShowNewFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [authRequired, setAuthRequired] = useState(false)
  const [globalDefaultView, setGlobalDefaultView] = useState<string>('source')
  const [editMode, setEditMode] = useState(false)
  const [rootDragOver, setRootDragOver] = useState(false)

  // Extract active folder path from URL
  const activePath = location.pathname.startsWith('/notes/')
    ? decodeURIComponent(location.pathname.slice(7))
    : ''

  // Extract active note ID from URL
  const noteMatch = location.pathname.match(/^\/note\/(\d+)/)
  const activeNoteId = noteMatch ? Number(noteMatch[1]) : null

  useEffect(() => {
    api.health().then(() => {
      loadFolders()
    }).catch(() => {})
    api.getSettings().then((s: SettingsType) => {
      setGlobalDefaultView(s.default_view || 'source')
    }).catch(err => {
      if (err.message === 'Unauthorized') setAuthRequired(true)
    })
  }, [])

  const loadFolders = () => {
    api.getFolderTree().then(setFolders).catch(() => {})
    api.listNotes({ root: 'true' }).then(setRootNotes).catch(() => {})
  }

  // Find parent folder ID for creating subfolders
  const findFolderByPath = (folders: FolderTree[], path: string): FolderTree | null => {
    const parts = path.split('/')
    let current: FolderTree | null = null
    let list = folders
    for (const part of parts) {
      current = list.find(f => f.slug === part) || null
      if (!current) return null
      list = current.children
    }
    return current
  }

  const activeFolder = activePath ? findFolderByPath(folders, activePath) : null

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return
    await api.createFolder({ name: newFolderName, parent_id: activeFolder?.id ?? null })
    setNewFolderName('')
    setShowNewFolder(false)
    loadFolders()
  }

  const handleDragStart = useCallback((e: React.DragEvent, noteId: number) => {
    e.dataTransfer.setData('text/plain', String(noteId))
    e.dataTransfer.effectAllowed = 'move'
  }, [])

  const handleDrop = useCallback(async (noteId: number, folderId: number | null) => {
    await api.updateNote(noteId, { folder_id: folderId })
    loadFolders()
  }, [])

  if (location.pathname === '/login') {
    return <LoginPage />
  }

  const isActive = (path: string) => location.pathname === path ? 'active' : ''

  return (
    <div className="layout">
      <div className="sidebar">
        <div className="sidebar-header">
          <Leaf size={24} />
          Leaf Note
        </div>
        <div className="sidebar-nav">
          <Link to="/" className={`sidebar-link ${isActive('/')}`}>
            <Home size={18} /> All Notes
          </Link>
          <Link to="/search" className={`sidebar-link ${isActive('/search')}`}>
            <Search size={18} /> Search
          </Link>
          <Link to="/settings" className={`sidebar-link ${isActive('/settings')}`}>
            <Settings size={18} /> Settings
          </Link>

          <div className="sidebar-section flex items-center justify-between">
            <span>Folders</span>
            <button className="btn-ghost btn-sm" onClick={() => setShowNewFolder(!showNewFolder)}>
              <Plus size={14} />
            </button>
          </div>

          {showNewFolder && (
            <div style={{ padding: '4px 12px' }}>
              <input
                placeholder="Folder name..."
                value={newFolderName}
                onChange={e => setNewFolderName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleCreateFolder()}
                autoFocus
              />
            </div>
          )}

          {folders.map(f => (
            <FolderTreeItem
              key={f.id}
              folder={f}
              activePath={activePath}
              activeNoteId={activeNoteId}
              onSelect={(path) => navigate(`/notes/${path}`)}
              editMode={editMode}
              onDragStart={handleDragStart}
              onDrop={handleDrop}
            />
          ))}

          {rootNotes.length > 0 && (
            <>
              <div
                className={`sidebar-section ${rootDragOver ? 'drag-over' : ''}`}
                onDragOver={editMode ? (e) => { e.preventDefault(); setRootDragOver(true) } : undefined}
                onDragLeave={() => setRootDragOver(false)}
                onDrop={editMode ? (e) => {
                  e.preventDefault()
                  setRootDragOver(false)
                  const noteId = Number(e.dataTransfer.getData('text/plain'))
                  if (noteId) handleDrop(noteId, null)
                } : undefined}
              >
                Uncategorized
              </div>
              {rootNotes.map(n => (
                <NoteItem key={n.id} note={n} active={activeNoteId === n.id}
                  editMode={editMode} onDragStart={handleDragStart} />
              ))}
            </>
          )}
        </div>
        <div className="sidebar-footer">
          <button
            className={`btn-ghost btn-sm ${editMode ? 'active' : ''}`}
            onClick={() => setEditMode(!editMode)}
            title={editMode ? 'Lock sidebar' : 'Enable drag & drop'}
          >
            {editMode ? <Unlock size={14} /> : <Lock size={14} />}
            <span style={{ marginLeft: 4, fontSize: 11 }}>{editMode ? 'Editing' : 'Locked'}</span>
          </button>
        </div>
      </div>
      <div className="main-content">
        <Routes>
          <Route path="/" element={<NotesPage onRefreshFolders={loadFolders} />} />
          <Route path="/notes/*" element={<NotesPage onRefreshFolders={loadFolders} />} />
          <Route path="/note/:id" element={<EditorPage onRefreshFolders={loadFolders} folders={folders} globalDefaultView={globalDefaultView} />} />
          <Route path="/note/new" element={<EditorPage onRefreshFolders={loadFolders} folders={folders} globalDefaultView={globalDefaultView} />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </div>
    </div>
  )
}
