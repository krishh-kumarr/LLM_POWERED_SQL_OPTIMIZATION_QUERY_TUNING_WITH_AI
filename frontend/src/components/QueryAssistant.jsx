import { useState, useEffect } from 'react'
import { Sparkles, Loader2, Play, Zap, AlertCircle, Code, MessageSquare } from 'lucide-react'
import { generateSQL, optimizeQuery, generateExampleQueries } from '../api/apiClient'

function QueryAssistant({ dbInfo, onQueryResults }) {
  const [mode, setMode] = useState('natural') // 'natural' or 'sql'
  const [naturalQuery, setNaturalQuery] = useState('')
  const [sqlQuery, setSqlQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [exampleQueries, setExampleQueries] = useState([
    'Show me all customers who made purchases in the last 30 days',
    'What are the top 5 best-selling products?',
    'Calculate total revenue by region',
    'Find customers who haven\'t made any orders',
    'Show average order value by product category',
  ])
  const [exampleQueriesLoading, setExampleQueriesLoading] = useState(false)

  // Generate example queries based on database schema when component mounts or dbInfo changes
  useEffect(() => {
    if (dbInfo && mode === 'natural') {
      setExampleQueriesLoading(true)
      generateExampleQueries(5)
        .then((response) => {
          if (response.success && response.example_queries && response.example_queries.length > 0) {
            setExampleQueries(response.example_queries)
          }
        })
        .catch((error) => {
          console.warn('Failed to generate example queries:', error)
          // Keep default queries on error
        })
        .finally(() => {
          setExampleQueriesLoading(false)
        })
    }
  }, [dbInfo, mode])

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    if (mode === 'natural' && !naturalQuery.trim()) {
      setError('Please enter a natural language query')
      return
    }
    
    if (mode === 'sql' && !sqlQuery.trim()) {
      setError('Please enter a SQL query')
      return
    }

    setLoading(true)
    setError(null)

    try {
      let sqlResult
      
      if (mode === 'natural') {
        // Generate optimized SQL from natural language
        console.log('Generating optimized SQL from natural language...')
        sqlResult = await generateSQL(naturalQuery)
      } else {
        // Optimize existing SQL query
        console.log('Optimizing existing SQL query...')
        sqlResult = await optimizeQuery(sqlQuery)
      }

      if (!sqlResult.success) {
        setError(sqlResult.message || 'Failed to process query')
        setLoading(false)
        return
      }

      // Combine all results (both modes return similar structure)
      const results = {
        mode: mode,
        original_query: mode === 'sql' ? sqlQuery : null,
        natural_query: mode === 'natural' ? naturalQuery : null,
        generated_sql: sqlResult.optimized_query || sqlResult.generated_sql,
        analysis: sqlResult.analysis || {},
        suggested_indexes: sqlResult.suggested_indexes || [],
        performance: sqlResult.performance || null,
        optimizations_applied: sqlResult.optimizations_applied || [],
        explanation: sqlResult.explanation || null,
      }

      onQueryResults(results)
      
    } catch (err) {
      console.error('Error:', err)
      
      // Handle timeout errors specifically
      if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        setError('Request timed out. The LLM is taking longer than expected. Please try again or check if Ollama is running.')
      } else if (err.response?.data?.message) {
        setError(err.response.data.message)
      } else if (err.message) {
        setError(err.message)
      } else {
        setError('An error occurred. Please check if the backend server and Ollama are running.')
      }
    } finally {
      setLoading(false)
    }
  }

  const loadExample = (query) => {
    setNaturalQuery(query)
    setError(null)
  }

  return (
    <div className="card">
      <div className="flex items-center gap-3 mb-6">
        <Sparkles className="w-8 h-8 text-primary-500" />
        <div>
          <h2 className="text-2xl font-bold text-white">AI Query Assistant</h2>
          <p className="text-slate-400 text-sm">
            Generate or optimize SQL queries using AI
          </p>
        </div>
      </div>

      {/* Mode Toggle */}
      <div className="mb-6">
        <div className="flex gap-2 bg-slate-800/50 p-1 rounded-lg border border-slate-700">
          <button
            type="button"
            onClick={() => {
              setMode('natural')
              setError(null)
            }}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
              mode === 'natural'
                ? 'bg-primary-600 text-white shadow-lg'
                : 'text-slate-400 hover:text-slate-300'
            }`}
          >
            <MessageSquare className="w-4 h-4" />
            Natural Language
          </button>
          <button
            type="button"
            onClick={() => {
              setMode('sql')
              setError(null)
            }}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
              mode === 'sql'
                ? 'bg-primary-600 text-white shadow-lg'
                : 'text-slate-400 hover:text-slate-300'
            }`}
          >
            <Code className="w-4 h-4" />
            SQL Query
          </button>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {mode === 'natural' ? (
          <div>
            <label htmlFor="natural-query" className="label">
              What would you like to know?
            </label>
            <textarea
              id="natural-query"
              value={naturalQuery}
              onChange={(e) => {
                setNaturalQuery(e.target.value)
                setError(null)
              }}
              placeholder="Example: Show me all customers who bought electronics in the last month..."
              rows={4}
              className="input resize-none font-sans"
              disabled={loading}
            />
          </div>
        ) : (
          <div>
            <label htmlFor="sql-query" className="label">
              Enter your SQL query to optimize
            </label>
            <textarea
              id="sql-query"
              value={sqlQuery}
              onChange={(e) => {
                setSqlQuery(e.target.value)
                setError(null)
              }}
              placeholder="SELECT * FROM customers WHERE age > 25..."
              rows={6}
              className="input resize-none font-mono text-sm"
              disabled={loading}
            />
            <p className="text-xs text-slate-400 mt-2">
              We'll analyze your query and optimize it using the database context
            </p>
          </div>
        )}

        {/* Error Message */}
        {error && (
          <div className="flex items-center gap-2 bg-red-500/20 border border-red-500/30 rounded-lg p-3 text-red-400">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <span className="text-sm">{error}</span>
          </div>
        )}

        <button
          type="submit"
          disabled={loading || (mode === 'natural' && !naturalQuery.trim()) || (mode === 'sql' && !sqlQuery.trim())}
          className="btn-primary w-full flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              {mode === 'natural' ? 'Generating SQL...' : 'Optimizing Query...'}
            </>
          ) : (
            <>
              <Zap className="w-5 h-5" />
              {mode === 'natural' ? 'Generate SQL' : 'Optimize Query'}
            </>
          )}
        </button>
      </form>

      {/* Example Queries - Only show for natural language mode */}
      {mode === 'natural' && (
        <div className="mt-6">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-300">Example Queries</h3>
            {exampleQueriesLoading && (
              <span className="text-xs text-slate-500 flex items-center gap-1">
                <Loader2 className="w-3 h-3 animate-spin" />
                Generating...
              </span>
            )}
          </div>
          {exampleQueriesLoading && exampleQueries.length === 5 && exampleQueries[0] === 'Show me all customers who made purchases in the last 30 days' ? (
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="w-full bg-slate-900 border border-slate-700 rounded-lg p-3 animate-pulse">
                  <div className="h-4 bg-slate-700 rounded w-3/4"></div>
                </div>
              ))}
            </div>
          ) : (
          <div className="space-y-2">
            {exampleQueries.map((query, index) => (
              <button
                key={index}
                onClick={() => loadExample(query)}
                disabled={loading}
                className="w-full text-left bg-slate-900 hover:bg-slate-800 border border-slate-700 hover:border-primary-500/50 rounded-lg p-3 text-sm text-slate-300 transition-all disabled:opacity-50 disabled:cursor-not-allowed group"
              >
                <div className="flex items-start gap-2">
                  <Play className="w-4 h-4 mt-0.5 text-slate-500 group-hover:text-primary-500 transition-colors" />
                  <span>{query}</span>
                </div>
              </button>
            ))}
          </div>
          )}
        </div>
      )}

      {/* Loading Info */}
      {loading && (
        <div className="mt-6 bg-primary-500/10 border border-primary-500/30 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <Loader2 className="w-5 h-5 text-primary-400 animate-spin" />
            <div className="flex-1">
              <p className="text-sm text-primary-400 font-medium">
                {mode === 'natural' ? 'Generating optimized SQL...' : 'Analyzing and optimizing your query...'}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                {mode === 'natural' 
                  ? 'Using RAG pipeline with Ollama Gemma:3b to generate optimized SQL'
                  : 'Using database context to optimize your SQL query'}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default QueryAssistant