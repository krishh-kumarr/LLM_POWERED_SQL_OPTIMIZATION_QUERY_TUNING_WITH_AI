import { useState } from 'react'
import { Database, Loader2, CheckCircle, AlertCircle } from 'lucide-react'
import { connectDatabase } from '../api/apiClient'

function DatabaseConnect({ onConnectionSuccess }) {
  const [dbType, setDbType] = useState('sqlite')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(false)

  const [formData, setFormData] = useState({
    host: 'localhost',
    port: '',
    database: 'sample_db',
    username: '',
    password: '',
    db_path: 'sample_db.sqlite',
  })

  const handleInputChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
    setError(null)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setSuccess(false)

    try {
      const config = {
        db_type: dbType,
        ...formData,
      }

      // Set default ports if not provided
      if (!config.port) {
        if (dbType === 'mysql') config.port = 3306
        if (dbType === 'postgresql') config.port = 5432
      }

      const response = await connectDatabase(config)

      if (response.success) {
        setSuccess(true)
        setTimeout(() => {
          onConnectionSuccess(response)
        }, 500)
      } else {
        setError(response.message || 'Connection failed')
      }
    } catch (err) {
      // Handle different types of errors with better messages
      let errorMessage = 'Failed to connect to database';
      
      if (err.response?.data?.message) {
        // Server responded with error message
        errorMessage = err.response.data.message;
      } else if (err.userMessage) {
        // Enhanced error message from interceptor
        errorMessage = err.userMessage;
      } else if (err.code === 'ECONNREFUSED' || err.message?.includes('Network Error') || err.message?.includes('ERR_CONNECTION_REFUSED')) {
        errorMessage = 'Cannot connect to backend server. Please ensure the Flask backend is running on http://localhost:5001. Start it with: cd backend && python app.py';
      } else if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        errorMessage = 'Connection timed out. The server is taking too long to respond.';
      } else if (err.message) {
        errorMessage = err.message;
      }
      
      console.error('Database connection error:', err);
      setError(errorMessage);
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <div className="flex items-center gap-3 mb-6">
        <Database className="w-8 h-8 text-primary-500" />
        <div>
          <h2 className="text-2xl font-bold text-white">Connect to Database</h2>
          <p className="text-slate-400 text-sm">Connect to your SQL database to get started</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Database Type Selection */}
        <div>
          <label className="label">Database Type</label>
          <div className="grid grid-cols-3 gap-3">
            {['sqlite', 'mysql', 'postgresql'].map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => setDbType(type)}
                className={`py-3 px-4 rounded-lg border-2 font-medium transition-all ${
                  dbType === type
                    ? 'border-primary-500 bg-primary-500/20 text-primary-400'
                    : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'
                }`}
              >
                {type.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {/* SQLite Configuration */}
        {dbType === 'sqlite' && (
          <div>
            <label htmlFor="db_path" className="label">
              Database File Path
            </label>
            <input
              type="text"
              id="db_path"
              name="db_path"
              value={formData.db_path}
              onChange={handleInputChange}
              placeholder="path/to/database.sqlite"
              className="input"
              required
            />
            <p className="mt-2 text-xs text-slate-400">
              💡 Use <code className="bg-slate-900 px-2 py-1 rounded">sample_db.sqlite</code> for the demo database
            </p>
          </div>
        )}

        {/* MySQL/PostgreSQL Configuration */}
        {(dbType === 'mysql' || dbType === 'postgresql') && (
          <>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="host" className="label">
                  Host
                </label>
                <input
                  type="text"
                  id="host"
                  name="host"
                  value={formData.host}
                  onChange={handleInputChange}
                  placeholder="localhost"
                  className="input"
                  required
                />
              </div>
              <div>
                <label htmlFor="port" className="label">
                  Port
                </label>
                <input
                  type="number"
                  id="port"
                  name="port"
                  value={formData.port}
                  onChange={handleInputChange}
                  placeholder={dbType === 'mysql' ? '3306' : '5432'}
                  className="input"
                />
              </div>
            </div>

            <div>
              <label htmlFor="database" className="label">
                Database Name
              </label>
              <input
                type="text"
                id="database"
                name="database"
                value={formData.database}
                onChange={handleInputChange}
                placeholder="my_database"
                className="input"
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="username" className="label">
                  Username
                </label>
                <input
                  type="text"
                  id="username"
                  name="username"
                  value={formData.username}
                  onChange={handleInputChange}
                  placeholder="root"
                  className="input"
                  required
                />
              </div>
              <div>
                <label htmlFor="password" className="label">
                  Password
                </label>
                <input
                  type="password"
                  id="password"
                  name="password"
                  value={formData.password}
                  onChange={handleInputChange}
                  placeholder="••••••••"
                  className="input"
                />
              </div>
            </div>
          </>
        )}

        {/* Error Message */}
        {error && (
          <div className="flex items-center gap-2 bg-red-500/20 border border-red-500/30 rounded-lg p-4 text-red-400">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <span className="text-sm">{error}</span>
          </div>
        )}

        {/* Success Message */}
        {success && (
          <div className="flex items-center gap-2 bg-green-500/20 border border-green-500/30 rounded-lg p-4 text-green-400">
            <CheckCircle className="w-5 h-5 flex-shrink-0" />
            <span className="text-sm">Connected successfully! Loading workspace...</span>
          </div>
        )}

        {/* Submit Button */}
        <button
          type="submit"
          disabled={loading || success}
          className="btn-primary w-full flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Connecting...
            </>
          ) : success ? (
            <>
              <CheckCircle className="w-5 h-5" />
              Connected
            </>
          ) : (
            <>
              <Database className="w-5 h-5" />
              Connect to Database
            </>
          )}
        </button>
      </form>

      {/* Info Box */}
      <div className="mt-6 bg-primary-500/10 border border-primary-500/30 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-primary-400 mb-2">Quick Start</h3>
        <p className="text-xs text-slate-300">
          Don't have a database? Use the included sample SQLite database with e-commerce data.
          Just keep the default path <code className="bg-slate-900 px-2 py-1 rounded">sample_db.sqlite</code> and click Connect.
        </p>
      </div>
    </div>
  )
}

export default DatabaseConnect
