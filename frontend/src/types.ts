export interface Tag {
  id: number
  name: string
  color: string
}

export interface Folder {
  id: number
  name: string
  slug: string
  parent_id: number | null
  created_at: string
  updated_at: string
}

export interface FolderTree extends Folder {
  children: FolderTree[]
  note_count: number
}

export interface NoteSummary {
  id: number
  title: string
  slug: string
  folder_id: number | null
  is_public: boolean
  pinned: boolean
  tags: Tag[]
  created_at: string
  updated_at: string
}

export interface Note extends NoteSummary {
  content: string
}

export interface SearchResult {
  notes: NoteSummary[]
  total: number
}

export interface Settings {
  auth_enabled: boolean
  api_key: string | null
  version: string
}
