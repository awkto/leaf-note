import { useState, useEffect } from 'react'
import { api } from '../api'
import { Settings as SettingsType } from '../types'
import { Key, Shield, RefreshCw, Copy } from 'lucide-react'

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsType | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    api.getSettings().then(setSettings).catch(() => {})
  }, [])

  const handleRegenKey = async () => {
    if (!confirm('Regenerate API key? The old key will stop working.')) return
    const res = await api.regenerateApiKey()
    setSettings(prev => prev ? { ...prev, api_key: res.api_key } : null)
  }

  const copyKey = () => {
    if (settings?.api_key) {
      navigator.clipboard.writeText(settings.api_key)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <>
      <div className="page-header">
        <h1>Settings</h1>
      </div>
      <div className="page-body" style={{ maxWidth: 600 }}>
        {settings && (
          <>
            <div style={{ marginBottom: 32 }}>
              <h3 className="flex items-center gap-2 mb-2">
                <Shield size={18} /> Authentication
              </h3>
              <p className="text-sm text-muted">
                {settings.auth_enabled
                  ? 'Authentication is enabled. All API requests require a valid token.'
                  : 'Authentication is disabled. All endpoints are accessible without credentials. Set auth_enabled: true in config.yaml to enable.'}
              </p>
            </div>

            {settings.auth_enabled && (
              <div style={{ marginBottom: 32 }}>
                <h3 className="flex items-center gap-2 mb-2">
                  <Key size={18} /> API Key
                </h3>
                <p className="text-sm text-muted mb-2">
                  Use this key in the Authorization header: <code>Bearer {'<api_key>'}</code>
                </p>
                {settings.api_key && (
                  <div className="flex gap-2 items-center">
                    <code style={{
                      background: 'var(--bg)', padding: '8px 12px', borderRadius: 'var(--radius)',
                      border: '1px solid var(--border)', fontSize: 13, flex: 1, wordBreak: 'break-all'
                    }}>
                      {settings.api_key}
                    </code>
                    <button className="btn-secondary btn-sm" onClick={copyKey}>
                      <Copy size={14} /> {copied ? 'Copied!' : 'Copy'}
                    </button>
                  </div>
                )}
                <button className="btn-secondary btn-sm mt-4" onClick={handleRegenKey}>
                  <RefreshCw size={14} /> Regenerate Key
                </button>
              </div>
            )}

            <div style={{ marginBottom: 32 }}>
              <h3 className="mb-2">Version</h3>
              <p className="text-sm text-muted">{settings.version}</p>
            </div>

            <div>
              <h3 className="mb-2">API Documentation</h3>
              <p className="text-sm text-muted">
                Interactive API docs available at <a href="/apidocs" target="_blank">/apidocs</a>
              </p>
            </div>

            {settings.auth_enabled && (
              <div className="mt-4">
                <button className="btn-danger btn-sm" onClick={() => {
                  localStorage.removeItem('leaf_token')
                  window.location.href = '/login'
                }}>
                  Sign Out
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </>
  )
}
