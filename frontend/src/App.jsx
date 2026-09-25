import { useState } from 'react'
import DatabaseConnect from './components/DatabaseConnect'
import QueryAssistant from './components/QueryAssistant'
import ResultsDashboard from './components/ResultsDashboard'
import SchemaViewer from './components/SchemaViewer'
import { Database, Sparkles } from 'lucide-react'

function App() {
  const [isConnected, setIsConnected] = useState(false)
  const [dbInfo, setDbInfo] = useState(null)
  const [queryResults, setQueryResults] = useState(null)

  const handleConnectionSuccess = (info) => {
    setIsConnected(true)
    setDbInfo(info)
  }

  const handleDisconnect = () => {
    setIsConnected(false)
    setDbInfo(null)
    setQueryResults(null)
  }

  const handleQueryResults = (results) => {
    setQueryResults(results)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <header className="bg-slate-800/50 backdrop-blur-sm border-b border-slate-700 sticky top-0 z-50">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="bg-primary-600 p-2 rounded-lg">
                <Sparkles className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-white">AI SQL Copilot</h1>
                <p className="text-sm text-slate-400">LLM-Powered SQL Optimization System</p>
              </div>
            </div>
            {isConnected && (
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 bg-green-500/20 text-green-400 px-4 py-2 rounded-lg border border-green-500/30">
                  <Database className="w-4 h-4" />
                  <span className="text-sm font-medium">
                    Connected to {dbInfo?.db_type || 'Database'}
                  </span>
                </div>
                <button
                  onClick={handleDisconnect}
                  className="btn-secondary"
                >
                  Disconnect
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8">
        {!isConnected ? (
          // Connection Screen
          <div className="max-w-2xl mx-auto">
            <DatabaseConnect onConnectionSuccess={handleConnectionSuccess} />
          </div>
        ) : (
          // Query Interface
          <div className="space-y-6">
            <SchemaViewer />
            <QueryAssistant 
              dbInfo={dbInfo} 
              onQueryResults={handleQueryResults}
            />
            {queryResults && (
              <ResultsDashboard results={queryResults} />
            )}
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="mt-16 py-6 border-t border-slate-700">
        <div className="container mx-auto px-4">
          <p className="text-center text-slate-400 text-sm">
            Powered by Ollama Gemma:3b • RAG Pipeline • LangChain
          </p>
        </div>
      </footer>
    </div>
  )
}

export default App