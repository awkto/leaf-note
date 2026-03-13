import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Leaf } from 'lucide-react'

export default function LoginPage() {
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isSetup, setIsSetup] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.health().then(async () => {
      try {
        await api.getSettings()
        // If settings accessible without auth, no login needed
        navigate('/', { replace: true })
      } catch {
        // Check if it's first-time setup
        try {
          const res = await fetch('/api/settings')
          if (res.status === 401) {
            // Auth enabled, check if admin exists
            setIsSetup(false)
          }
        } catch {}
      }
    }).finally(() => setLoading(false))
  }, [navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      let res
      if (isSetup) {
        res = await api.setup(password)
      } else {
        res = await api.login(password)
      }
      if (res.token) {
        localStorage.setItem('leaf_token', res.token)
      }
      navigate('/', { replace: true })
    } catch (err: any) {
      setError(err.message || 'Login failed')
    }
  }

  if (loading) return null

  return (
    <div className="login-page">
      <div className="login-card">
        <h1><Leaf size={28} /> Leaf Note</h1>
        <p>{isSetup ? 'Set up your admin password' : 'Enter your password to continue'}</p>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoFocus
            />
          </div>
          {error && <p className="text-danger text-sm mb-2">{error}</p>}
          <button className="btn-primary" style={{ width: '100%' }} type="submit">
            {isSetup ? 'Set Password' : 'Login'}
          </button>
        </form>
        {!isSetup && (
          <p className="text-sm text-muted mt-4" style={{ textAlign: 'center' }}>
            <button className="btn-ghost text-sm" onClick={() => setIsSetup(true)}>
              First time? Set up admin
            </button>
          </p>
        )}
      </div>
    </div>
  )
}
