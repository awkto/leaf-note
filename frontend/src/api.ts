const getHeaders = (): Record<string, string> => {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = localStorage.getItem('leaf_token')
  if (token) headers['Authorization'] = `Bearer ${token}`
  return headers
}

const handleRes = async (res: Response) => {
  if (res.status === 401) {
    localStorage.removeItem('leaf_token')
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  // Notes
  listNotes: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return fetch(`/api/notes${qs}`, { headers: getHeaders() }).then(handleRes)
  },
  getNote: (id: number) =>
    fetch(`/api/notes/${id}`, { headers: getHeaders() }).then(handleRes),
  createNote: (data: any) =>
    fetch('/api/notes', { method: 'POST', headers: getHeaders(), body: JSON.stringify(data) }).then(handleRes),
  updateNote: (id: number, data: any) =>
    fetch(`/api/notes/${id}`, { method: 'PUT', headers: getHeaders(), body: JSON.stringify(data) }).then(handleRes),
  deleteNote: (id: number) =>
    fetch(`/api/notes/${id}`, { method: 'DELETE', headers: getHeaders() }).then(handleRes),
  browseByPath: (path: string) =>
    fetch(`/api/notes/${path}`, { headers: getHeaders() }).then(handleRes),
  getFolderByPath: (path: string) =>
    fetch(`/api/folders/by-path/${path}`, { headers: getHeaders() }).then(handleRes),

  // Folders
  listFolders: (parentId?: number) => {
    const qs = parentId !== undefined ? `?parent_id=${parentId}` : ''
    return fetch(`/api/folders${qs}`, { headers: getHeaders() }).then(handleRes)
  },
  getFolderTree: () =>
    fetch('/api/folders/tree', { headers: getHeaders() }).then(handleRes),
  createFolder: (data: any) =>
    fetch('/api/folders', { method: 'POST', headers: getHeaders(), body: JSON.stringify(data) }).then(handleRes),
  updateFolder: (id: number, data: any) =>
    fetch(`/api/folders/${id}`, { method: 'PUT', headers: getHeaders(), body: JSON.stringify(data) }).then(handleRes),
  deleteFolder: (id: number) =>
    fetch(`/api/folders/${id}`, { method: 'DELETE', headers: getHeaders() }).then(handleRes),

  // Tags
  listTags: () =>
    fetch('/api/tags', { headers: getHeaders() }).then(handleRes),
  createTag: (data: any) =>
    fetch('/api/tags', { method: 'POST', headers: getHeaders(), body: JSON.stringify(data) }).then(handleRes),
  deleteTag: (id: number) =>
    fetch(`/api/tags/${id}`, { method: 'DELETE', headers: getHeaders() }).then(handleRes),

  // Search
  search: (q: string, tag?: string) => {
    const params = new URLSearchParams({ q })
    if (tag) params.set('tag', tag)
    return fetch(`/api/search?${params}`, { headers: getHeaders() }).then(handleRes)
  },

  // Export
  exportAll: () => {
    const headers = getHeaders()
    delete headers['Content-Type']
    return fetch('/api/export/markdown', { headers }).then(res => res.blob())
  },
  exportNote: (id: number) => {
    const headers = getHeaders()
    delete headers['Content-Type']
    return fetch(`/api/export/note/${id}`, { headers }).then(res => res.blob())
  },

  // Import
  importMarkdown: (files: FileList, folderId?: number) => {
    const formData = new FormData()
    Array.from(files).forEach(f => formData.append('files', f))
    const headers: Record<string, string> = {}
    const token = localStorage.getItem('leaf_token')
    if (token) headers['Authorization'] = `Bearer ${token}`
    const qs = folderId ? `?folder_id=${folderId}` : ''
    return fetch(`/api/import/markdown${qs}`, { method: 'POST', headers, body: formData }).then(handleRes)
  },

  // Images
  uploadImage: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    const headers: Record<string, string> = {}
    const token = localStorage.getItem('leaf_token')
    if (token) headers['Authorization'] = `Bearer ${token}`
    return fetch('/api/images', { method: 'POST', headers, body: formData }).then(handleRes)
  },

  // Settings
  getSettings: () =>
    fetch('/api/settings', { headers: getHeaders() }).then(handleRes),
  login: (password: string) =>
    fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password }) }).then(handleRes),
  setup: (password: string) =>
    fetch('/api/auth/setup', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ admin_password: password }) }).then(handleRes),
  regenerateApiKey: () =>
    fetch('/api/auth/regenerate-api-key', { method: 'POST', headers: getHeaders() }).then(handleRes),
  setDefaultView: (view: string) =>
    fetch('/api/settings/default-view', { method: 'PUT', headers: getHeaders(), body: JSON.stringify({ default_view: view }) }).then(handleRes),
  health: () =>
    fetch('/api/health').then(handleRes),
}
