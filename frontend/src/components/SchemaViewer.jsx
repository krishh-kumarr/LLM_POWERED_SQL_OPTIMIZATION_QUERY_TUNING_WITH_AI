import { useState, useEffect } from 'react'
import {
  Database, ChevronDown, ChevronRight, Key, Link as LinkIcon, AlertTriangle
} from 'lucide-react'
import { getSchema } from '../api/apiClient'

function SchemaViewer() {
  const [schemaData, setSchemaData] = useState(null)
  const [schemaLoading, setSchemaLoading] = useState(false)
  const [schemaError, setSchemaError] = useState(null)
  const [expandedTables, setExpandedTables] = useState(new Set())
  const [isCollapsed, setIsCollapsed] = useState(false)

  useEffect(() => {
    console.log('🔍 SchemaViewer: Fetching schema on mount...')
    setSchemaLoading(true)
    setSchemaError(null)
    getSchema()
      .then((response) => {
        console.log('✅ SchemaViewer: Received schema response:', response)
        if (response.success) {
          setSchemaData(response.schema)
          console.log('📊 SchemaViewer: Schema data set:', response.schema)
        } else {
          const errorMsg = response.message || 'Failed to load schema'
          console.error('❌ SchemaViewer: Schema fetch failed:', errorMsg)
          setSchemaError(errorMsg)
        }
      })
      .catch((error) => {
        const errorMsg = error.response?.data?.message || error.message || 'Failed to load schema'
        console.error('❌ SchemaViewer: Schema fetch error:', errorMsg, error)
        setSchemaError(errorMsg)
      })
      .finally(() => {
        setSchemaLoading(false)
      })
  }, [])

  const toggleTable = (tableName) => {
    setExpandedTables((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(tableName)) {
        newSet.delete(tableName)
      } else {
        newSet.add(tableName)
      }
      return newSet
    })
  }

  if (isCollapsed) {
    return (
      <div className="card">
        <button
          onClick={() => setIsCollapsed(false)}
          className="w-full flex items-center justify-between text-left"
        >
          <div className="flex items-center gap-3">
            <Database className="w-5 h-5 text-primary-400" />
            <h3 className="text-lg font-semibold text-white">Database Schema</h3>
            {schemaData && (
              <span className="text-xs text-slate-400">
                {schemaData.tables?.length || 0} tables • {schemaData.relationships?.length || 0} relationships
              </span>
            )}
          </div>
          <ChevronRight className="w-5 h-5 text-slate-400" />
        </button>
      </div>
    )
  }

  return (
    <div className="card">
      <button
        onClick={() => setIsCollapsed(true)}
        className="w-full flex items-center justify-between text-left mb-4"
      >
        <div className="flex items-center gap-3">
          <Database className="w-5 h-5 text-primary-400" />
          <h3 className="text-lg font-semibold text-white">Database Schema</h3>
          {schemaData && (
            <span className="text-xs text-slate-400">
              {schemaData.tables?.length || 0} tables • {schemaData.relationships?.length || 0} relationships
            </span>
          )}
        </div>
        <ChevronDown className="w-5 h-5 text-slate-400" />
      </button>

      {schemaLoading && (
        <div className="text-center py-8">
          <Database className="w-12 h-12 text-slate-500 mx-auto mb-4 animate-pulse" />
          <p className="text-slate-400">Loading schema...</p>
        </div>
      )}

      {schemaError && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400" />
            <div>
              <h4 className="text-sm font-semibold text-red-400">Error Loading Schema</h4>
              <p className="text-xs text-slate-300 mt-1">{schemaError}</p>
            </div>
          </div>
        </div>
      )}

      {schemaData && !schemaLoading && (
        <div className="space-y-4">
          {/* Tables List */}
          {schemaData.tables && schemaData.tables.length > 0 && (
            <div className="space-y-3">
              {schemaData.tables.map((table, idx) => {
                const isExpanded = expandedTables.has(table.name)
                return (
                  <div key={idx} className="bg-slate-900 rounded-lg border border-slate-700">
                    <button
                      onClick={() => toggleTable(table.name)}
                      className="w-full flex items-center justify-between text-left p-3 hover:bg-slate-800/50 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        {isExpanded ? (
                          <ChevronDown className="w-4 h-4 text-slate-400" />
                        ) : (
                          <ChevronRight className="w-4 h-4 text-slate-400" />
                        )}
                        <h4 className="text-base font-semibold text-white">{table.name}</h4>
                        <span className="text-xs text-slate-400 bg-slate-800 px-2 py-1 rounded">
                          {table.columns?.length || 0} columns
                        </span>
                        {table.primary_keys && table.primary_keys.length > 0 && (
                          <span className="text-xs text-yellow-400 bg-yellow-500/20 px-2 py-1 rounded flex items-center gap-1">
                            <Key className="w-3 h-3" />
                            {table.primary_keys.length} PK
                          </span>
                        )}
                        {table.foreign_keys && table.foreign_keys.length > 0 && (
                          <span className="text-xs text-blue-400 bg-blue-500/20 px-2 py-1 rounded flex items-center gap-1">
                            <LinkIcon className="w-3 h-3" />
                            {table.foreign_keys.length} FK
                          </span>
                        )}
                      </div>
                    </button>

                    {isExpanded && (
                      <div className="px-3 pb-3 space-y-3">
                        {/* Columns */}
                        {table.columns && table.columns.length > 0 && (
                          <div>
                            <h5 className="text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wide">Columns</h5>
                            <div className="overflow-x-auto">
                              <table className="w-full text-xs">
                                <thead>
                                  <tr className="border-b border-slate-700">
                                    <th className="text-left py-2 px-2 text-slate-400 font-medium">Name</th>
                                    <th className="text-left py-2 px-2 text-slate-400 font-medium">Type</th>
                                    <th className="text-left py-2 px-2 text-slate-400 font-medium">Nullable</th>
                                    <th className="text-left py-2 px-2 text-slate-400 font-medium">Default</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {table.columns.map((column, colIdx) => {
                                    const isPrimaryKey = table.primary_keys?.includes(column.name)
                                    const isForeignKey = table.foreign_keys?.some(
                                      (fk) => fk.constrained_columns?.includes(column.name)
                                    )
                                    return (
                                      <tr key={colIdx} className="border-b border-slate-800 hover:bg-slate-800/50">
                                        <td className="py-2 px-2 text-slate-300">
                                          <div className="flex items-center gap-2">
                                            {isPrimaryKey && (
                                              <Key className="w-3 h-3 text-yellow-400" title="Primary Key" />
                                            )}
                                            {isForeignKey && (
                                              <LinkIcon className="w-3 h-3 text-blue-400" title="Foreign Key" />
                                            )}
                                            <span className="font-medium">{column.name}</span>
                                          </div>
                                        </td>
                                        <td className="py-2 px-2 text-slate-400 font-mono">
                                          {column.type}
                                        </td>
                                        <td className="py-2 px-2">
                                          {column.nullable ? (
                                            <span className="text-green-400">Yes</span>
                                          ) : (
                                            <span className="text-red-400">No</span>
                                          )}
                                        </td>
                                        <td className="py-2 px-2 text-slate-400">
                                          {column.default || <span className="text-slate-600">—</span>}
                                        </td>
                                      </tr>
                                    )
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}

                        {/* Foreign Keys */}
                        {table.foreign_keys && table.foreign_keys.length > 0 && (
                          <div>
                            <h5 className="text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wide flex items-center gap-2">
                              <LinkIcon className="w-3 h-3 text-blue-400" />
                              Foreign Keys
                            </h5>
                            <div className="space-y-2">
                              {table.foreign_keys.map((fk, fkIdx) => (
                                <div key={fkIdx} className="bg-slate-950 rounded p-2 border border-slate-700">
                                  <div className="flex items-center gap-2 text-xs">
                                    <span className="text-slate-300">
                                      {fk.constrained_columns?.join(', ')}
                                    </span>
                                    <span className="text-slate-500">→</span>
                                    <span className="text-blue-400 font-medium">
                                      {fk.referred_table}.{fk.referred_columns?.join(', ')}
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* Relationships Overview */}
          {schemaData.relationships && schemaData.relationships.length > 0 && (
            <div className="mt-4 pt-4 border-t border-slate-700">
              <h4 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
                <LinkIcon className="w-4 h-4 text-blue-400" />
                Table Relationships
              </h4>
              <div className="space-y-2">
                {schemaData.relationships.map((rel, idx) => (
                  <div key={idx} className="bg-slate-900 rounded p-2 border border-slate-700">
                    <div className="flex items-center gap-2 text-xs">
                      <span className="text-white font-medium">{rel.from_table}</span>
                      <span className="text-slate-500">({rel.from_columns?.join(', ')})</span>
                      <span className="text-blue-400">→</span>
                      <span className="text-white font-medium">{rel.to_table}</span>
                      <span className="text-slate-500">({rel.to_columns?.join(', ')})</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {(!schemaData.tables || schemaData.tables.length === 0) && (
            <div className="text-center py-8">
              <Database className="w-12 h-12 text-slate-500 mx-auto mb-4" />
              <p className="text-slate-400">No tables found in the database</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default SchemaViewer
