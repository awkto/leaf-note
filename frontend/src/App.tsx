import { Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { api } from './api'
import { FolderTree, Settings } from './types'
import NotesPage from './pages/NotesPage'
import EditorPage from './pages/EditorPage'
import SearchPage from './pages/SearchPage'
import SettingsPage from './pages/SettingsPage'
import LoginPage from './pages/LoginPage'
import {
  FileText, Search, Settings, FolderOpen, ChevronRight, ChevronDown,
  Plus, Leaf, Tag, Home
} from 'lucide-react'

function FolderTreeItem({ folder, depth = 0, activeFolderId, onSelect }: {
  folder: FolderTree; depth?: number; activeFolderId: number | null;
  onSelect: (id: number | null) => void
}) {
  const [open, setOpen] = useState(true)
  const hasChildren = folder.children.length > 0

  return (
    <div>
      <div
        className={`folder-item ${activeFolderId === folder.id ? 'active' : ''}`}
        style={{ paddingLeft: 12 + depth * 16 }}
        onClick={() => onSelect(folder.id)}
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
              activeFolderId={activeFolderId} onSelect={onSelect} />
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
  const [activeFolderId, setActiveFolderId] = useState<number | null>(null)
  const [showNewFolder, setShowNewFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [authRequired, setAuthRequired] = useState(false)
  const [globalDefaultView, setGlobalDefaultView] = useState<string>('source')

  useEffect(() => {
    api.health().then(h => {
      loadFolders()
    }).catch(() => {})
    api.getSettings().then((s: Settings) => {
      setGlobalDefaultView(s.default_view || 'source')
    }).catch(err => {
      if (err.message === 'Unauthorized') setAuthRequired(true)
    })
  }, [])

  const loadFolders = () => {
    api.getFolderTree().then(setFolders).catch(() => {})
  }

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return
    await api.createFolder({ name: newFolderName, parent_id: activeFolderId })
    setNewFolderName('')
    setShowNewFolder(false)
    loadFolders()
  }

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

          <div
            className={`folder-item ${activeFolderId === null ? 'active' : ''}`}
            onClick={() => { setActiveFolderId(null); navigate('/') }}
          >
            <span style={{ width: 14 }} />
            <FileText size={14} />
            <span>Uncategorized</span>
          </div>

          {folders.map(f => (
            <FolderTreeItem
              key={f.id}
              folder={f}
              activeFolderId={activeFolderId}
              onSelect={(id) => { setActiveFolderId(id); navigate('/') }}
            />
          ))}
        </div>
      </div>
      <div className="main-content">
        <Routes>
          <Route path="/" element={<NotesPage folderId={activeFolderId} onRefreshFolders={loadFolders} />} />
          <Route path="/note/:id" element={<EditorPage onRefreshFolders={loadFolders} folders={folders} globalDefaultView={globalDefaultView} />} />
          <Route path="/note/new" element={<EditorPage onRefreshFolders={loadFolders} folders={folders} globalDefaultView={globalDefaultView} />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </div>
    </div>
  )
}
