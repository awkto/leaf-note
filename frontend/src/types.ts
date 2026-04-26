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
  default_view: string | null
  created_at: string
  updated_at: string
}

export interface FolderNoteRef {
  id: number
  title: string
  slug: string
  pinned: boolean
}

export interface FolderTree extends Folder {
  children: FolderTree[]
  note_count: number
  notes: FolderNoteRef[]
}

export interface NoteSummary {
  id: number
  title: string
  slug: string
  folder_id: number | null
  is_public: boolean
  pinned: boolean
  default_view: string | null
  tags: Tag[]
  excerpt: string
  created_at: string
  updated_at: string
}

export interface Note extends NoteSummary {
  content: string
  permalink: string
}

export interface SearchResult {
  notes: NoteSummary[]
  total: number
}

export interface Settings {
  auth_enabled: boolean
  api_key: string | null
  version: string
  default_view: string
}

export interface ReplicaMeta {
  last_pushed_data_version?: number
  last_pushed_at?: string
  last_pushed_size_bytes?: number
  last_pushed_raw_bytes?: number
  last_received_data_version?: string
  last_received_at?: string
  last_received_size_bytes?: number
  last_received_raw_bytes?: number
  sender_id?: string
  last_seen_peer_at?: string
  peer_replication_paused?: boolean
}

export interface BackupInfo {
  name: string
  size_bytes: number
  mtime: string
}

export interface HAStatus {
  enabled: boolean
  role: 'primary' | 'standby'
  self_id?: string
  peer_id?: string
  peer_url?: string
  peer_reachable?: boolean
  peer_role?: string | null
  replication_paused?: boolean
  is_orphaned?: boolean
  last_promoted_at?: string | null
  last_demoted_at?: string | null
  sync_interval_seconds?: number
  replica_meta?: ReplicaMeta
  last_backup?: BackupInfo | null
  data_version?: number | null
}
