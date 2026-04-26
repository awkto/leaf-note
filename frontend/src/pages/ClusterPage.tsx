import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import { HAStatus } from '../types'
import {
  Network, RefreshCw, Power, Pause, Play, AlertTriangle,
  Copy, Check, LogOut, Database, Clock, Send, Inbox, Eye, Zap,
} from 'lucide-react'

const fmtBytes = (n?: number) => {
  if (!n && n !== 0) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

const fmtAge = (iso?: string | null) => {
  if (!iso) return 'never'
  const t = new Date(iso).getTime()
  const ageS = Math.floor((Date.now() - t) / 1000)
  if (ageS < 0) return 'just now'
  if (ageS < 60) return `${ageS}s ago`
  if (ageS < 3600) return `${Math.floor(ageS / 60)}m ${ageS % 60}s ago`
  if (ageS < 86400) return `${Math.floor(ageS / 3600)}h ago`
  return `${Math.floor(ageS / 86400)}d ago`
}

export default function ClusterPage() {
  const [status, setStatus] = useState<HAStatus | null>(null)
  const [error, setError] = useState<string>('')
  const [busy, setBusy] = useState<string>('')
  const [, setTick] = useState(0) // re-render for "Xs ago"

  // Pairing UI
  const [myBaseUrl, setMyBaseUrl] = useState('')
  const [pairingSecret, setPairingSecret] = useState<string>('')
  const [pasteSecret, setPasteSecret] = useState('')
  const [pasteBaseUrl, setPasteBaseUrl] = useState('')
  const [copied, setCopied] = useState(false)

  const reload = useCallback(async () => {
    try {
      const s = await api.haStatus()
      setStatus(s)
      setError('')
    } catch (e: any) {
      setError(e.message || 'failed to load HA status')
    }
  }, [])

  useEffect(() => {
    reload()
    const status_iv = setInterval(reload, 5000)
    const tick_iv = setInterval(() => setTick(x => x + 1), 1000)
    setMyBaseUrl(window.location.origin)
    setPasteBaseUrl(window.location.origin)
    return () => { clearInterval(status_iv); clearInterval(tick_iv) }
  }, [reload])

  const run = async (label: string, fn: () => Promise<any>, confirmMsg?: string) => {
    if (confirmMsg && !confirm(confirmMsg)) return
    setBusy(label); setError('')
    try {
      await fn()
      await reload()
    } catch (e: any) {
      setError(e.message || 'failed')
    } finally {
      setBusy('')
    }
  }

  const generatePairing = async () => {
    setBusy('generate'); setError('')
    try {
      const r = await api.haGeneratePairing(myBaseUrl)
      setPairingSecret(r.pairing_secret)
      await reload()
    } catch (e: any) {
      setError(e.message || 'failed')
    } finally {
      setBusy('')
    }
  }

  const acceptPairing = async () => {
    if (!pasteSecret.trim()) { setError('paste a pairing secret first'); return }
    setBusy('accept'); setError('')
    try {
      const r = await api.haAcceptPairing(pasteSecret.trim(), pasteBaseUrl)
      setPasteSecret('')
      if (!r.peer_reachable) {
        setError(`paired but peer not reachable yet (${r.register_msg || ''})`)
      }
      await reload()
    } catch (e: any) {
      setError(e.message || 'failed')
    } finally {
      setBusy('')
    }
  }

  const copySecret = () => {
    navigator.clipboard.writeText(pairingSecret)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (!status) {
    return (
      <>
        <div className="page-header"><h1>Cluster</h1></div>
        <div className="page-body">{error || 'Loading...'}</div>
      </>
    )
  }

  const enabled = status.enabled
  const role = status.role
  const meta = status.replica_meta || {}
  const lastSyncIso = role === 'primary' ? meta.last_pushed_at : meta.last_received_at
  const lastSeen = meta.last_seen_peer_at
  const isOrphaned = !!status.is_orphaned
  const isPaused = !!status.replication_paused
  const peerReachable = !!status.peer_reachable

  // -------------------------------------------------------------------------
  // First-run / unpaired view
  // -------------------------------------------------------------------------
  if (!enabled) {
    return (
      <>
        <div className="page-header"><h1>Cluster</h1></div>
        <div className="page-body" style={{ maxWidth: 760 }}>
          <div className="status-banner status-info">
            <Network size={18} /> HA is not configured on this node. Set up a primary by generating a pairing secret, or paste one received from a primary to join as standby.
          </div>

          {error && <div className="status-banner status-error" style={{ marginTop: 16 }}><AlertTriangle size={16} /> {error}</div>}

          <h3 className="mt-4 mb-2">Make this node the primary</h3>
          <p className="text-sm text-muted mb-2">
            Generates a pairing secret bundling the HA token and KEK. Paste it on the standby's Cluster page within a few minutes.
          </p>
          <div className="flex gap-2 mb-2 items-center">
            <label className="text-sm" style={{ minWidth: 110 }}>This node's URL</label>
            <input
              value={myBaseUrl}
              onChange={e => setMyBaseUrl(e.target.value)}
              placeholder="https://leaf.example.com"
              style={{ flex: 1 }}
            />
            <button className="btn-primary btn-sm" onClick={generatePairing} disabled={busy === 'generate'}>
              {busy === 'generate' ? 'Generating...' : 'Generate pairing secret'}
            </button>
          </div>

          {pairingSecret && (
            <div className="mt-2">
              <p className="text-sm text-muted mb-2">Copy this and paste it on the standby:</p>
              <div className="flex gap-2 items-start">
                <code style={{
                  background: 'var(--bg)', padding: '8px 12px', borderRadius: 'var(--radius)',
                  border: '1px solid var(--border)', fontSize: 12, flex: 1, wordBreak: 'break-all',
                  maxHeight: 120, overflow: 'auto',
                }}>{pairingSecret}</code>
                <button className="btn-secondary btn-sm" onClick={copySecret}>
                  {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? 'Copied' : 'Copy'}
                </button>
              </div>
            </div>
          )}

          <h3 className="mt-4 mb-2">Or join an existing primary as standby</h3>
          <p className="text-sm text-muted mb-2">
            Paste the pairing secret generated on the primary. This node's data will be overwritten by the primary's snapshot on the first sync.
          </p>
          <div className="flex gap-2 mb-2 items-center">
            <label className="text-sm" style={{ minWidth: 110 }}>This node's URL</label>
            <input
              value={pasteBaseUrl}
              onChange={e => setPasteBaseUrl(e.target.value)}
              placeholder="https://leaf-standby.example.com"
              style={{ flex: 1 }}
            />
          </div>
          <textarea
            value={pasteSecret}
            onChange={e => setPasteSecret(e.target.value)}
            placeholder="paste pairing secret here..."
            rows={3}
            style={{ width: '100%', fontFamily: 'monospace', fontSize: 12 }}
          />
          <button className="btn-primary btn-sm mt-2" onClick={acceptPairing} disabled={busy === 'accept'}>
            {busy === 'accept' ? 'Pairing...' : 'Accept pairing & become standby'}
          </button>
        </div>
      </>
    )
  }

  // -------------------------------------------------------------------------
  // Paired view
  // -------------------------------------------------------------------------
  const roleColor = role === 'primary' ? 'var(--accent)' : '#f59e0b'

  return (
    <>
      <div className="page-header"><h1>Cluster</h1></div>
      <div className="page-body" style={{ maxWidth: 820 }}>

        <div className="cluster-grid">
          <div className="cluster-card">
            <div className="cluster-card-label">This node</div>
            <div className="cluster-card-value" style={{ color: roleColor }}>
              {role === 'primary' ? <Zap size={18} /> : <Inbox size={18} />}
              {role.toUpperCase()}
            </div>
            <div className="cluster-card-meta">id {status.self_id} · data_version {status.data_version ?? '—'}</div>
          </div>

          <div className="cluster-card">
            <div className="cluster-card-label">Peer ({status.peer_id})</div>
            <div className="cluster-card-value" style={{ color: peerReachable ? '#22c55e' : '#ef4444' }}>
              <Network size={18} />
              {peerReachable ? 'reachable' : 'unreachable'}
            </div>
            <div className="cluster-card-meta" style={{ wordBreak: 'break-all' }}>
              {status.peer_url || '(not set)'}
            </div>
          </div>

          <div className="cluster-card">
            <div className="cluster-card-label">Last sync</div>
            <div className="cluster-card-value">
              <Clock size={18} />
              {fmtAge(lastSyncIso)}
            </div>
            <div className="cluster-card-meta">
              every {status.sync_interval_seconds}s
              {role === 'primary' && meta.last_pushed_size_bytes ? ` · pushed ${fmtBytes(meta.last_pushed_size_bytes)}` : ''}
              {role === 'standby' && meta.last_received_size_bytes ? ` · received ${fmtBytes(meta.last_received_size_bytes)}` : ''}
            </div>
          </div>

          <div className="cluster-card">
            <div className="cluster-card-label">Last seen peer</div>
            <div className="cluster-card-value">
              <Eye size={18} />
              {fmtAge(lastSeen)}
            </div>
            <div className="cluster-card-meta">
              {isPaused ? 'replication paused' : isOrphaned ? 'primary paused replication' : 'replicating'}
            </div>
          </div>
        </div>

        {error && <div className="status-banner status-error" style={{ marginTop: 16 }}><AlertTriangle size={16} /> {error}</div>}
        {isOrphaned && <div className="status-banner status-warn" style={{ marginTop: 16 }}><AlertTriangle size={16} /> Primary has paused replication. Your data may be stale.</div>}
        {isPaused && role === 'primary' && <div className="status-banner status-warn" style={{ marginTop: 16 }}><Pause size={16} /> Replication is paused. Standby will not receive updates.</div>}

        <h3 className="mt-4 mb-2">Actions</h3>
        <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
          {role === 'primary' && (
            <>
              <button
                className="btn-primary btn-sm"
                onClick={() => run('sync', () => api.haSyncNow())}
                disabled={busy === 'sync'}
              >
                <Send size={14} /> {busy === 'sync' ? 'Syncing...' : 'Sync now'}
              </button>
              <button
                className="btn-secondary btn-sm"
                onClick={() => run('pause', () => api.haUpdateConfig({ replication_paused: !isPaused }))}
                disabled={busy === 'pause'}
              >
                {isPaused ? <Play size={14} /> : <Pause size={14} />} {isPaused ? 'Resume replication' : 'Pause replication'}
              </button>
            </>
          )}

          {role === 'standby' && (
            <>
              <button
                className="btn-primary btn-sm"
                onClick={() => run(
                  'failover',
                  () => api.haFailover(false),
                  'Promote this standby to primary?\n\nThe peer will be told to demote itself. The replica DB on this node will be moved into place.',
                )}
                disabled={busy === 'failover'}
              >
                <Power size={14} /> {busy === 'failover' ? 'Promoting...' : 'Trigger failover'}
              </button>
              <button
                className="btn-danger btn-sm"
                onClick={() => run(
                  'failover-force',
                  () => api.haFailover(true),
                  'FORCE failover to primary?\n\nUse this only when you are certain the peer is dead. Promoting while the peer is still primary causes split-brain.',
                )}
                disabled={busy === 'failover-force'}
              >
                <AlertTriangle size={14} /> {busy === 'failover-force' ? 'Forcing...' : 'Force failover'}
              </button>
              <button
                className="btn-danger btn-sm"
                onClick={() => run(
                  'leave',
                  () => api.haLeaveCluster(),
                  'Leave the cluster?\n\nThis WIPES the local replica and HA state on this node and returns it to first-run. The primary is unaffected.',
                )}
                disabled={busy === 'leave'}
              >
                <LogOut size={14} /> {busy === 'leave' ? 'Leaving...' : 'Leave cluster'}
              </button>
            </>
          )}

          <button
            className="btn-secondary btn-sm"
            onClick={() => run('backup', () => api.haTriggerBackup())}
            disabled={busy === 'backup'}
          >
            <Database size={14} /> {busy === 'backup' ? 'Backing up...' : 'Run local backup now'}
          </button>

          <button
            className="btn-ghost btn-sm"
            onClick={reload}
          >
            <RefreshCw size={14} /> Refresh
          </button>
        </div>

        <h3 className="mt-4 mb-2">Replica details</h3>
        <pre style={{
          background: 'var(--bg)', padding: 12, borderRadius: 'var(--radius)',
          border: '1px solid var(--border)', fontSize: 12, overflow: 'auto',
        }}>{JSON.stringify({ replica_meta: meta, last_backup: status.last_backup }, null, 2)}</pre>

      </div>
    </>
  )
}
