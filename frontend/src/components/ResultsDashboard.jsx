import { useState } from 'react'
import {
  TrendingUp,
  Database,
  Lightbulb,
  AlertTriangle,
  Copy,
  Check,
  Code,
  Clock,
  ArrowRight,
  Sparkles,
} from 'lucide-react'

// Query Plan Viewer Component
function QueryPlanViewer({ plan }) {
  if (!plan || plan.length === 0) {
    return (
      <div className="bg-slate-900 rounded-lg p-4 border border-slate-700">
        <p className="text-slate-400">No query plan available</p>
      </div>
    )
  }

  // ---------------------------
  // Helpers for MySQL JSON plan
  // ---------------------------

  const normalizeMySQLTableNode = (table) => {
    if (!table || typeof table !== 'object') return null

    const accessType = table.access_type || ''
    let nodeType = 'Table Access'

    if (accessType === 'ALL') {
      nodeType = 'Full Table Scan'
    } else if (accessType) {
      nodeType = `${accessType} access`
    }

    const children = []

    // nested_loop children
    if (Array.isArray(table.nested_loop)) {
      for (const child of table.nested_loop) {
        if (child.table) {
          const childNode = normalizeMySQLTableNode(child.table)
          if (childNode) children.push(childNode)
        } else if (child.query_block) {
          const childNode = normalizeMySQLQueryBlock(child.query_block)
          if (childNode) children.push(childNode)
        }
      }
    }

    const rawRows =
      table.rows_produced_per_join ??
      table.rows_examined_per_scan ??
      table.rows_examined_per_scan ??
      null
    const rows =
      rawRows != null && !Number.isNaN(Number(rawRows))
        ? Number(rawRows)
        : null

    let cost = null
    if (table.cost_info && table.cost_info.query_cost != null) {
      const parsed = Number(table.cost_info.query_cost)
      cost = !Number.isNaN(parsed) ? parsed : null
    }

    return {
      'Node Type': nodeType,
      table_name: table.table_name,
      rows,
      cost,
      filter: table.attached_condition,
      Plans: children.length > 0 ? children : undefined,
    }
  }

  const normalizeMySQLQueryBlock = (queryBlock) => {
    if (!queryBlock || typeof queryBlock !== 'object') return null

    const children = []

    // handle optimized_away_subqueries
    if (Array.isArray(queryBlock.optimized_away_subqueries)) {
      for (const opt of queryBlock.optimized_away_subqueries) {
        if (opt && opt.query_block) {
          const childQB = normalizeMySQLQueryBlock(opt.query_block)
          if (childQB) {
            children.push({
              'Node Type': 'Optimized Away Subquery',
              message: queryBlock.message || opt.message,
              Plans: [childQB],
            })
          }
        }
      }
    }

    // existing nested_loop handling
    if (Array.isArray(queryBlock.nested_loop)) {
      for (const child of queryBlock.nested_loop) {
        if (child.table) {
          const tableNode = normalizeMySQLTableNode(child.table)
          if (tableNode) children.push(tableNode)
        } else if (child.query_block) {
          const qbNode = normalizeMySQLQueryBlock(child.query_block)
          if (qbNode) children.push(qbNode)
        }
      }
    } else if (queryBlock.table) {
      const tableNode = normalizeMySQLTableNode(queryBlock.table)
      if (tableNode) children.push(tableNode)
    }

    let cost = null
    if (queryBlock.cost_info && queryBlock.cost_info.query_cost != null) {
      const parsed = Number(queryBlock.cost_info.query_cost)
      cost = !Number.isNaN(parsed) ? parsed : null
    }

    // Rough rows from first child if present
    const firstChild = children[0]
    const rows =
      firstChild && firstChild.rows != null ? firstChild.rows : null

    return {
      'Node Type': 'Query Block',
      message: queryBlock.message,
      rows,
      cost,
      Plans: children.length > 0 ? children : undefined,
    }
  }

  const normalizeMySQLPlan = (parsed) => {
    // parsed may be { query_block: {...} } or [ { query_block: {...} } ]
    if (!parsed || typeof parsed !== 'object') return parsed

    if (parsed.query_block) {
      return normalizeMySQLQueryBlock(parsed.query_block)
    }

    if (Array.isArray(parsed) && parsed[0]?.query_block) {
      return normalizeMySQLQueryBlock(parsed[0].query_block)
    }

    return parsed
  }

  // Detect plan format (SQLite, PostgreSQL, MySQL, or generic)
  const detectPlanFormat = () => {
    const firstItem = plan[0]
    if (!firstItem || typeof firstItem !== 'object') return 'unknown'

    // SQLite format typically has: id, selectid, order, from, detail
    if ('detail' in firstItem || 'order' in firstItem) {
      return 'sqlite'
    }

    // PostgreSQL JSON format
    if (firstItem.Plan || firstItem['Node Type'] || firstItem['Operation']) {
      return 'postgresql'
    }

    // MySQL JSON format
    if (firstItem.query_block || firstItem.select_id !== undefined) {
      return 'mysql'
    }

    // Try to detect JSON string in any field (e.g. MySQL "EXPLAIN" column)
    const firstKey = Object.keys(firstItem)[0]
    if (firstKey && typeof firstItem[firstKey] === 'string') {
      try {
        const parsed = JSON.parse(firstItem[firstKey])
        if (parsed.Plan) return 'postgresql'
        if (parsed.query_block) return 'mysql'
        if (Array.isArray(parsed) && parsed[0]?.query_block) return 'mysql'
      } catch (e) {
        // Not JSON
      }
    }

    return 'generic'
  }

  const format = detectPlanFormat()

  // Render SQLite plan (table format)
  const renderSQLitePlan = () => {
    return (
      <div className="bg-slate-900 rounded-lg p-4 border border-slate-700 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700">
              <th className="text-left py-2 px-3 text-slate-400 font-medium">
                Step
              </th>
              <th className="text-left py-2 px-3 text-slate-400 font-medium">
                Select
              </th>
              <th className="text-left py-2 px-3 text-slate-400 font-medium">
                Order
              </th>
              <th className="text-left py-2 px-3 text-slate-400 font-medium">
                From
              </th>
              <th className="text-left py-2 px-3 text-slate-400 font-medium">
                Detail
              </th>
            </tr>
          </thead>
          <tbody>
            {plan.map((item, idx) => (
              <tr
                key={idx}
                className="border-b border-slate-800 hover:bg-slate-800/50"
              >
                <td className="py-2 px-3 text-slate-300">{item.id ?? idx}</td>
                <td className="py-2 px-3 text-slate-300">
                  {item.selectid ?? '-'}
                </td>
                <td className="py-2 px-3 text-slate-300">
                  {item.order ?? '-'}
                </td>
                <td className="py-2 px-3 text-slate-300">
                  {item.from ?? '-'}
                </td>
                <td className="py-2 px-3 text-slate-300 font-mono text-xs">
                  {item.detail ?? JSON.stringify(item)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  // Render structured plan (PostgreSQL/MySQL/Generic)
  const renderStructuredPlan = () => {
    const renderPlanNode = (
      node,
      depth = 0,
      isNested = false,
      keyPrefix = 'root'
    ) => {
      if (!node || typeof node !== 'object') return null

      const indent = depth * 24

      const rawNodeType =
        node['Node Type'] ||
        node.operation ||
        node.type ||
        node.Operation ||
        'Unknown'
      const nodeType =
        typeof rawNodeType === 'string'
          ? rawNodeType
          : String(rawNodeType ?? 'Unknown')

      const relationName =
        node['Relation Name'] || node.table_name || node.table || ''
      const alias = node['Alias'] || node.alias || ''

      // message from MySQL query_block / subquery
      const message = node.message || node.Message || node['Message']

      const rawCost = node['Total Cost'] ?? node.cost ?? node['cost']
      const cost =
        rawCost != null && !Number.isNaN(Number(rawCost))
          ? Number(rawCost)
          : null

      const rawRows = node['Plan Rows'] ?? node.rows ?? node['rows']
      const rows =
        rawRows != null && !Number.isNaN(Number(rawRows))
          ? Number(rawRows)
          : null

      const rawWidth = node['Plan Width'] ?? node.width
      const width =
        rawWidth != null && !Number.isNaN(Number(rawWidth))
          ? Number(rawWidth)
          : null

      const rawActualRows = node['Actual Rows'] ?? node['actual_rows']
      const actualRows =
        rawActualRows != null && !Number.isNaN(Number(rawActualRows))
          ? Number(rawActualRows)
          : null

      const rawActualTime =
        node['Actual Total Time'] ?? node['actual_total_time']
      const actualTime =
        rawActualTime != null && !Number.isNaN(Number(rawActualTime))
          ? Number(rawActualTime)
          : null

      const filter = node['Filter'] || node.filter
      const joinType = node['Join Type'] || node.join_type
      const indexName = node['Index Name'] || node.index_name

      const isFullScan =
        nodeType.toLowerCase().includes('scan') &&
        !indexName &&
        (!relationName || !String(relationName).includes('Index'))

      const isExpensive = cost != null && cost > 1000

      return (
        <div key={keyPrefix} className="mb-2">
          <div
            className={`flex items-start gap-3 p-3 rounded-lg border ${
              isFullScan
                ? 'bg-red-500/10 border-red-500/30'
                : isExpensive
                ? 'bg-yellow-500/10 border-yellow-500/30'
                : 'bg-slate-800/50 border-slate-700'
            }`}
            style={{ marginLeft: `${indent}px` }}
          >
            {isNested && (
              <ArrowRight className="w-4 h-4 text-slate-500 mt-1 flex-shrink-0" />
            )}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span
                  className={`font-semibold ${
                    isFullScan
                      ? 'text-red-400'
                      : isExpensive
                      ? 'text-yellow-400'
                      : 'text-blue-400'
                  }`}
                >
                  {nodeType}
                </span>
                {relationName && (
                  <>
                    <span className="text-slate-500">on</span>
                    <span className="text-green-400 font-mono">
                      {relationName}
                    </span>
                  </>
                )}
                {alias && alias !== relationName && (
                  <span className="text-slate-400 text-sm">({alias})</span>
                )}
                {indexName && (
                  <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-1 rounded">
                    using {indexName}
                  </span>
                )}
                {joinType && (
                  <span className="text-xs bg-purple-500/20 text-purple-400 px-2 py-1 rounded">
                    {joinType}
                  </span>
                )}
              </div>

              {/* show message / note from query_block */}
              {message && (
                <div className="mt-1 text-xs text-slate-400">{message}</div>
              )}

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-2 text-xs">
                {cost != null && (
                  <div>
                    <span className="text-slate-500">Cost:</span>
                    <span className="text-slate-300 ml-1 font-mono">
                      {cost}
                    </span>
                  </div>
                )}
                {rows != null && (
                  <div>
                    <span className="text-slate-500">Est. Rows:</span>
                    <span className="text-slate-300 ml-1 font-mono">
                      {rows.toLocaleString()}
                    </span>
                  </div>
                )}
                {actualRows != null && (
                  <div>
                    <span className="text-slate-500">Actual Rows:</span>
                    <span className="text-slate-300 ml-1 font-mono">
                      {actualRows.toLocaleString()}
                    </span>
                  </div>
                )}
                {actualTime != null && (
                  <div>
                    <span className="text-slate-500">Time:</span>
                    <span className="text-slate-300 ml-1 font-mono">
                      {actualTime.toFixed(2)} ms
                    </span>
                  </div>
                )}
                {width != null && (
                  <div>
                    <span className="text-slate-500">Width:</span>
                    <span className="text-slate-300 ml-1 font-mono">
                      {width}
                    </span>
                  </div>
                )}
              </div>

              {filter && (
                <div className="mt-2 text-xs">
                  <span className="text-slate-500">Filter:</span>
                  <span className="text-slate-300 ml-2 font-mono">
                    {filter}
                  </span>
                </div>
              )}

              {isFullScan && (
                <div className="mt-2 flex items-center gap-2 text-xs text-red-400">
                  <AlertTriangle className="w-4 h-4" />
                  <span>
                    Full table scan detected - consider adding an index
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Recursively render child plans */}
          {node.Plans &&
            Array.isArray(node.Plans) &&
            node.Plans.map((child, idx) =>
              renderPlanNode(child, depth + 1, true, `${keyPrefix}-${idx}`)
            )}
        </div>
      )
    }

    // Try to extract plan from different formats
    let planData = plan

    if (Array.isArray(plan) && plan.length > 0) {
      const first = plan[0]

      // PostgreSQL JSON format might be nested
      if (first.Plan) {
        planData = [first.Plan]
      } else if (typeof first === 'object') {
        const firstKey = Object.keys(first)[0]
        if (firstKey && typeof first[firstKey] === 'string') {
          // Often MySQL EXPLAIN JSON is in a single string column (e.g., "EXPLAIN")
          try {
            const parsed = JSON.parse(first[firstKey])

            if (parsed.Plan) {
              // Postgres FORMAT JSON
              planData = [parsed.Plan]
            } else if (Array.isArray(parsed) && parsed[0]?.Plan) {
              planData = [parsed[0].Plan]
            } else if (
              parsed.query_block ||
              (Array.isArray(parsed) && parsed[0]?.query_block)
            ) {
              // MySQL JSON → normalize
              const normalized = normalizeMySQLPlan(parsed)
              planData = [normalized]
            }
          } catch (e) {
            // Not JSON, use as-is
          }
        } else if (first.query_block) {
          // MySQL JSON already parsed
          const normalized = normalizeMySQLPlan(first)
          planData = [normalized]
        }
      }
    }

    return (
      <div className="space-y-2">
        {planData.map((item, idx) => {
          if (typeof item === 'object') {
            return renderPlanNode(item, 0, false, `root-${idx}`)
          }
          return (
            <div
              key={idx}
              className="bg-slate-900 rounded-lg p-4 border border-slate-700"
            >
              <pre className="text-sm text-slate-300 whitespace-pre-wrap">
                {JSON.stringify(item, null, 2)}
              </pre>
            </div>
          )
        })}
      </div>
    )
  }

  // Render based on format
  if (format === 'sqlite') {
    return renderSQLitePlan()
  }

  return (
    <div>
      {renderStructuredPlan()}
      <div className="mt-4 p-3 bg-slate-900/50 rounded-lg border border-slate-700">
        <details className="text-sm">
          <summary className="cursor-pointer text-slate-400 hover:text-slate-300">
            View Raw JSON
          </summary>
          <pre className="mt-2 text-xs text-slate-400 overflow-x-auto">
            {JSON.stringify(plan, null, 2)}
          </pre>
        </details>
      </div>
    </div>
  )
}

function ResultsDashboard({ results }) {
  const [activeTab, setActiveTab] = useState('overview')
  const [copiedSQL, setCopiedSQL] = useState(false)

  if (!results) return null

  const {
    mode = 'natural',
    natural_query,
    original_query,
    generated_sql,
    optimized_query,
    is_already_optimized,
    optimizations_applied = [],
    explanation,
    analysis,
    suggested_indexes = [],
    performance = null,
  } = results

  // Use optimized_query if available (SQL mode), otherwise use generated_sql (natural mode)
  const final_sql = optimized_query || generated_sql || ''

  const copyToClipboard = async (text) => {
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
      setCopiedSQL(true)
      setTimeout(() => setCopiedSQL(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const tabs = [
    { id: 'overview', label: 'Overview', icon: TrendingUp },
    { id: 'queries', label: 'SQL Query', icon: Code },
    { id: 'performance', label: 'Performance', icon: Clock },
    { id: 'suggestions', label: 'Suggestions', icon: Lightbulb },
  ]

  // Helpers for safe numeric rendering
  const formatMs = (value, fallback = 'N/A') =>
    value != null && !Number.isNaN(Number(value))
      ? `${Number(value).toFixed(2)} ms`
      : fallback

  const formatNumber = (value, fallback = 'N/A') =>
    value != null && !Number.isNaN(Number(value))
      ? Number(value).toLocaleString()
      : fallback

  const formatCpu = (value, fallback = '0.00 %') =>
    value != null && !Number.isNaN(Number(value))
      ? `${Number(value).toFixed(2)} %`
      : fallback

  // Comparison helpers (for SQL mode)
  const comparison = performance?.comparison || null

  const originalTotalTime =
    comparison?.original?.total_time_ms ??
    comparison?.original?.execution_time_ms ??
    null

  const optimizedTotalTime =
    comparison?.optimized?.total_time_ms ??
    comparison?.optimized?.execution_time_ms ??
    null

  // Detect if original vs optimized plans look structurally identical
  const plansLookIdentical =
    !!comparison?.original?.query_plan &&
    !!comparison?.optimized?.query_plan &&
    JSON.stringify(comparison.original.query_plan) ===
      JSON.stringify(comparison.optimized.query_plan)

  return (
    <div className="space-y-6">
      {/* Tabs */}
      <div className="card">
        <div className="flex gap-2 overflow-x-auto pb-2">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all whitespace-nowrap ${
                  activeTab === tab.id
                    ? 'bg-primary-600 text-white'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Natural Query or Original Query */}
          {mode === 'natural' ? (
            <div className="card">
              <h3 className="text-lg font-semibold text-white mb-3">
                Your Question
              </h3>
              <p className="text-slate-300 bg-slate-900 rounded-lg p-4 border border-slate-700">
                {natural_query}
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Original Query */}
              <div className="card">
                <h3 className="text-lg font-semibold text-white mb-3">
                  Original Query
                </h3>
                <div className="bg-slate-900 rounded-lg p-4 border border-slate-700">
                  <code className="text-sm text-slate-300 font-mono whitespace-pre-wrap break-words">
                    {original_query}
                  </code>
                </div>
              </div>

              {/* Optimization Status */}
              {is_already_optimized ? (
                <div className="card bg-green-500/10 border-green-500/30">
                  <div className="flex items-center gap-3">
                    <div className="bg-green-500/20 p-2 rounded-lg">
                      <Check className="w-5 h-5 text-green-400" />
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold text-green-400">
                        Already Optimized
                      </h3>
                      <p className="text-sm text-slate-300 mt-1">
                        {explanation}
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="card bg-primary-500/10 border-primary-500/30">
                  <div className="flex items-center gap-3">
                    <div className="bg-primary-500/20 p-2 rounded-lg">
                      <Lightbulb className="w-5 h-5 text-primary-400" />
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold text-primary-400">
                        Optimizations Applied
                      </h3>
                      {explanation && (
                        <p className="text-sm text-slate-300 mt-1">
                          {explanation}
                        </p>
                      )}
                      {optimizations_applied.length > 0 && (
                        <ul className="mt-2 space-y-1">
                          {optimizations_applied.map((opt, idx) => (
                            <li
                              key={idx}
                              className="text-sm text-slate-300 flex items-start gap-2"
                            >
                              <span className="text-primary-400 mt-1">•</span>
                              <span>{opt}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Quick Stats */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="card">
              <div className="flex items-center gap-3">
                <div className="bg-primary-500/20 p-3 rounded-lg">
                  <Code className="w-6 h-6 text-primary-400" />
                </div>
                <div>
                  <p className="text-sm text-slate-400">Query Complexity</p>
                  <p className="text-xl font-bold text-white capitalize">
                    {analysis?.complexity || 'N/A'}
                  </p>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="flex items-center gap-3">
                <div className="bg-yellow-500/20 p-3 rounded-lg">
                  <AlertTriangle className="w-6 h-6 text-yellow-400" />
                </div>
                <div>
                  <p className="text-sm text-slate-400">Issues Found</p>
                  <p className="text-xl font-bold text-white">
                    {analysis?.issues?.length || 0}
                  </p>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="flex items-center gap-3">
                <div className="bg-blue-500/20 p-3 rounded-lg">
                  <Database className="w-6 h-6 text-blue-400" />
                </div>
                <div>
                  <p className="text-sm text-slate-400">Index Suggestions</p>
                  <p className="text-xl font-bold text-white">
                    {suggested_indexes?.length || 0}
                  </p>
                </div>
              </div>
            </div>

            {/* Optimizations Applied Count (SQL mode only) */}
            {mode === 'sql' && optimizations_applied.length > 0 && (
              <div className="card">
                <div className="flex items-center gap-3">
                  <div className="bg-purple-500/20 p-3 rounded-lg">
                    <Lightbulb className="w-6 h-6 text-purple-400" />
                  </div>
                  <div>
                    <p className="text-sm text-slate-400">
                      Optimizations Applied
                    </p>
                    <p className="text-xl font-bold text-white">
                      {optimizations_applied.length}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Performance Metrics Summary */}
          {performance && (
            <div className="card">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Clock className="w-5 h-5 text-green-400" />
                Performance Metrics
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                {/* DB Execution Time */}
                <div className="bg-slate-900 rounded-lg p-4 border border-slate-700">
                  <p className="text-xs text-slate-400 mb-1">
                    DB Execution Time
                  </p>
                  <p className="text-2xl font-bold text-blue-400">
                    {formatMs(performance.db_execution_time_ms)}
                  </p>
                  {performance.db_execution_time_ms != null ? (
                    <>
                      {performance.db_timing_source && (
                        <p className="text-xs text-slate-500 mt-1">
                          {performance.db_timing_source === 'explain_analyze'
                            ? 'EXPLAIN ANALYZE'
                            : performance.db_timing_source}
                        </p>
                      )}
                      <p className="text-xs text-slate-500 mt-0.5">
                        {performance.timing_source === 'database'
                          ? 'Server-side'
                          : 'Client-side (wall clock)'}
                      </p>
                    </>
                  ) : (
                    <p className="text-xs text-slate-500 mt-1">
                      Not available
                    </p>
                  )}
                </div>

                {/* Client Time */}
                <div className="bg-slate-900 rounded-lg p-4 border border-slate-700">
                  <p className="text-xs text-slate-400 mb-1">Client Time</p>
                  <p className="text-2xl font-bold text-green-400">
                    {(() => {
                      const totalTime =
                        performance.total_time_ms ||
                        performance.execution_time_ms ||
                        0
                      const dbTime = performance.db_execution_time_ms || 0
                      const clientTime =
                        dbTime > 0 && dbTime < totalTime
                          ? totalTime - dbTime
                          : totalTime
                      return `${clientTime.toFixed(2)} ms`
                    })()}
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    Client-side processing (fetch + convert)
                  </p>
                </div>

                {/* CPU Usage */}
                <div className="bg-slate-900 rounded-lg p-4 border border-slate-700">
                  <p className="text-xs text-slate-400 mb-1">CPU Usage</p>
                  <p className="text-2xl font-bold text-white">
                    {formatCpu(performance.cpu_percent)}
                  </p>
                </div>

                {/* Rows Returned */}
                <div className="bg-slate-900 rounded-lg p-4 border border-slate-700">
                  <p className="text-xs text-slate-400 mb-1">Rows Returned</p>
                  <p className="text-2xl font-bold text-white">
                    {formatNumber(performance.row_count)}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Queries Tab */}
      {activeTab === 'queries' && (
        <div className="space-y-6">
          {/* Generated/Optimized Query */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <Code className="w-5 h-5 text-primary-400" />
                {mode === 'sql' ? 'Optimized SQL Query' : 'Generated SQL Query'}
              </h3>
              <button
                onClick={() => copyToClipboard(final_sql)}
                disabled={!final_sql}
                className={`btn-secondary flex items-center gap-2 text-sm ${
                  !final_sql ? 'opacity-60 cursor-not-allowed' : ''
                }`}
              >
                {copiedSQL ? (
                  <>
                    <Check className="w-4 h-4" />
                    Copied!
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    Copy
                  </>
                )}
              </button>
            </div>
            <pre className="bg-slate-900 rounded-lg p-4 overflow-x-auto border border-slate-700">
              <code className="text-sm text-slate-300 font-mono whitespace-pre-wrap break-words">
                {final_sql || '-- No SQL generated.'}
              </code>
            </pre>
            <div className="mt-4 bg-primary-500/10 border border-primary-500/30 rounded-lg p-4">
              <p className="text-sm text-primary-400 font-medium mb-2">
                ℹ️ About this query
              </p>
              <p className="text-sm text-slate-300">
                {mode === 'sql'
                  ? 'This SQL query has been optimized using database context and best practices. It uses the data dictionary to ensure table and column names are correct.'
                  : "This SQL query has been generated with optimization best practices, including specific column selection, efficient JOINs, and proper filtering. It's ready to use in production."}
              </p>
            </div>
          </div>

          {/* Show Original Query in SQL mode */}
          {mode === 'sql' &&
            original_query &&
            original_query !== final_sql && (
              <div className="card">
                <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                  <Code className="w-5 h-5 text-slate-400" />
                  Original Query (Before Optimization)
                </h3>
                <pre className="bg-slate-900 rounded-lg p-4 overflow-x-auto border border-slate-700">
                  <code className="text-sm text-slate-400 font-mono whitespace-pre-wrap break-words">
                    {original_query}
                  </code>
                </pre>
              </div>
            )}
        </div>
      )}

      {/* Performance Tab */}
      {activeTab === 'performance' && (
        <div className="space-y-6">
          {performance ? (
            <>
              {/* Comparison View (SQL Optimization Mode) */}
              {mode === 'sql' &&
                performance.comparison &&
                !is_already_optimized && (
                  <div className="card bg-gradient-to-r from-primary-500/10 to-green-500/10 border-primary-500/30">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                      <TrendingUp className="w-5 h-5 text-green-400" />
                      Performance Comparison: Original vs Optimized
                    </h3>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      {/* Original Query Performance */}
                      <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700">
                        <h4 className="text-sm font-semibold text-slate-400 mb-3">
                          Original Query
                        </h4>
                        <div className="space-y-3">
                          {/* Total Time (overall) */}
                          <div>
                            <p className="text-xs text-slate-500 mb-1">
                              Total Time (DB + client)
                            </p>
                            <p className="text-xl font-bold text-white">
                              {formatMs(originalTotalTime)}
                            </p>
                          </div>

                          {/* DB Execution Time */}
                          <div>
                            <p className="text-xs text-slate-500 mb-1">
                              DB Execution Time
                            </p>
                            {performance.comparison.original
                              .db_execution_time_ms != null ? (
                              <>
                                <p className="text-xl font-bold text-blue-400">
                                  {formatMs(
                                    performance.comparison.original
                                      .db_execution_time_ms
                                  )}
                                </p>
                                <p className="text-xs text-slate-500 mt-0.5">
                                  {performance.comparison.original
                                    .db_timing_source
                                    ? 'Server-side'
                                    : 'Client-side (wall clock)'}
                                </p>
                              </>
                            ) : (
                              <>
                                <p className="text-xl font-bold text-blue-400">
                                  N/A
                                </p>
                                <p className="text-xs text-slate-500 mt-0.5">
                                  Not measured
                                </p>
                              </>
                            )}
                          </div>

                          {/* Client Time */}
                          <div>
                            <p className="text-xs text-slate-500 mb-1">
                              Client Time
                            </p>
                            <p className="text-xl font-bold text-slate-300">
                              {(() => {
                                const totalTime =
                                  performance.comparison.original
                                    .total_time_ms ||
                                  performance.comparison.original
                                    .execution_time_ms ||
                                  0
                                const dbTime =
                                  performance.comparison.original
                                    .db_execution_time_ms || 0
                                const clientTime =
                                  dbTime > 0 && dbTime < totalTime
                                    ? totalTime - dbTime
                                    : totalTime
                                return `${clientTime.toFixed(2)} ms`
                              })()}
                            </p>
                            <p className="text-xs text-slate-500 mt-0.5">
                              Client-side processing (fetch + convert)
                            </p>
                          </div>

                          {/* CPU Usage */}
                          <div>
                            <p className="text-xs text-slate-500 mb-1">
                              CPU Usage
                            </p>
                            <p className="text-xl font-bold text-slate-300">
                              {formatCpu(
                                performance.comparison.original.cpu_percent
                              )}
                            </p>
                          </div>
                        </div>
                      </div>

                      {/* Optimized Query Performance */}
                      <div className="bg-green-500/10 rounded-lg p-4 border border-green-500/30">
                        <h4 className="text-sm font-semibold text-green-400 mb-3">
                          Optimized Query
                        </h4>
                        <div className="space-y-3">
                          {/* Total Time (overall) */}
                          <div>
                            <p className="text-xs text-slate-500 mb-1">
                              Total Time (DB + client)
                            </p>
                            <div className="flex items-center gap-2">
                              <p className="text-xl font-bold text-white">
                                {formatMs(optimizedTotalTime)}
                              </p>
                              {comparison?.is_faster && (
                                <span className="text-xs bg-green-500/20 text-green-400 px-2 py-1 rounded">
                                  ↓
                                  {Math.abs(
                                    comparison.time_improvement_percent
                                  ).toFixed(1)}
                                  %
                                </span>
                              )}
                            </div>
                            {comparison?.is_faster &&
                              comparison.time_improvement_ms != null && (
                                <p className="text-xs text-green-400 mt-1">
                                  Faster by{' '}
                                  {Math.abs(
                                    comparison.time_improvement_ms
                                  ).toFixed(2)}{' '}
                                  ms
                                </p>
                              )}
                          </div>

                          {/* DB Execution Time */}
                          <div>
                            <p className="text-xs text-slate-500 mb-1">
                              DB Execution Time
                            </p>
                            {performance.db_execution_time_ms != null ? (
                              <>
                                <p className="text-xl font-bold text-blue-400">
                                  {formatMs(performance.db_execution_time_ms)}
                                </p>
                                <p className="text-xs text-slate-500 mt-0.5">
                                  {performance.db_timing_source
                                    ? 'Server-side'
                                    : 'Client-side (wall clock)'}
                                </p>
                              </>
                            ) : (
                              <>
                                <p className="text-xl font-bold text-blue-400">
                                  N/A
                                </p>
                                <p className="text-xs text-slate-500 mt-0.5">
                                  Not measured
                                </p>
                              </>
                            )}
                          </div>

                          {/* Client Time */}
                          <div>
                            <p className="text-xs text-slate-500 mb-1">
                              Client Time
                            </p>
                            <p className="text-xl font-bold text-green-400">
                              {(() => {
                                const totalTime =
                                  performance.total_time_ms ||
                                  performance.execution_time_ms ||
                                  0
                                const dbTime =
                                  performance.db_execution_time_ms || 0
                                const clientTime =
                                  dbTime > 0 && dbTime < totalTime
                                    ? totalTime - dbTime
                                    : totalTime
                                return `${clientTime.toFixed(2)} ms`
                              })()}
                            </p>
                            <p className="text-xs text-slate-500 mt-0.5">
                              Client-side processing (fetch + convert)
                            </p>
                          </div>

                          {/* CPU Usage */}
                          <div>
                            <p className="text-xs text-slate-500 mb-1">
                              CPU Usage
                            </p>
                            <p className="text-xl font-bold text-green-400">
                              {formatCpu(performance.cpu_percent)}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Improvement Summary */}
                    <div className="mt-4 pt-4 border-t border-slate-700">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-semibold text-white">
                            Overall Improvement
                          </p>
                          <p className="text-xs text-slate-400 mt-1">
                            {performance.comparison.is_faster
                              ? 'Query execution is faster'
                              : 'Performance metrics available'}
                          </p>
                        </div>
                        {performance.comparison.is_faster && (
                          <div className="bg-green-500/20 text-green-400 px-4 py-2 rounded-lg border border-green-500/30">
                            <p className="text-sm font-bold">✓ Optimized</p>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Readability-only optimization note when plans are identical */}
                    {plansLookIdentical && (
                      <div className="mt-3 text-xs text-slate-400 bg-slate-900/70 border border-slate-700 rounded-lg p-3">
                        <p>
                          The original query was already logically optimal.
                          Improvements applied were primarily for readability
                          and modern SQL style.
                        </p>
                      </div>
                    )}
                  </div>
                )}

              {/* Performance Metrics Cards */}
              {(mode === 'natural' ||
                is_already_optimized ||
                !performance.comparison) && (
                <div className="card mb-4">
                  <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                    <Clock className="w-5 h-5 text-primary-400" />
                    {mode === 'sql' && is_already_optimized
                      ? 'Query Performance (Already Optimized)'
                      : mode === 'sql'
                      ? 'Optimized Query Performance'
                      : 'Query Performance'}
                  </h3>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                {/* DB Execution Time Card */}
                <div className="card">
                  <div className="flex items-center gap-3">
                    <div className="bg-blue-500/20 p-3 rounded-lg">
                      <Database className="w-6 h-6 text-blue-400" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm text-slate-400">
                        DB Execution Time
                      </p>
                      <p className="text-2xl font-bold text-blue-400">
                        {formatMs(performance.db_execution_time_ms)}
                      </p>
                      {performance.db_execution_time_ms != null ? (
                        <>
                          {performance.db_timing_source && (
                            <p className="text-xs text-slate-500 mt-1">
                              {performance.db_timing_source ===
                              'explain_analyze'
                                ? 'EXPLAIN ANALYZE'
                                : performance.db_timing_source}
                            </p>
                          )}
                          <p className="text-xs text-slate-500 mt-0.5">
                            {performance.timing_source === 'database'
                              ? 'Server-side processing'
                              : 'Client-side (wall clock)'}
                          </p>
                        </>
                      ) : (
                        <p className="text-xs text-slate-500 mt-1">
                          Not measured
                        </p>
                      )}
                    </div>
                  </div>
                </div>

                {/* Client Time Card */}
                <div className="card">
                  <div className="flex items-center gap-3">
                    <div className="bg-green-500/20 p-3 rounded-lg">
                      <Clock className="w-6 h-6 text-green-400" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm text-slate-400">Client Time</p>
                      <p className="text-2xl font-bold text-green-400">
                        {(() => {
                          const totalTime =
                            performance.total_time_ms ||
                            performance.execution_time_ms ||
                            0
                          const dbTime =
                            performance.db_execution_time_ms || 0
                          const clientTime =
                            dbTime > 0 && dbTime < totalTime
                              ? totalTime - dbTime
                              : totalTime
                          return `${clientTime.toFixed(2)} ms`
                        })()}
                      </p>
                      {/* Enhanced timing breakdown */}
                      {(performance.fetch_time_ms != null ||
                        performance.conversion_time_ms != null ||
                        performance.network_time_ms != null) && (
                        <div className="text-xs text-slate-500 mt-1 space-y-0.5">
                          {performance.fetch_time_ms != null && (
                            <p>
                              Fetch:{' '}
                              {performance.fetch_time_ms.toFixed(2)}
                              ms
                            </p>
                          )}
                          {performance.conversion_time_ms != null &&
                            performance.conversion_time_ms > 0 && (
                              <p>
                                Convert:{' '}
                                {performance.conversion_time_ms.toFixed(
                                  2
                                )}
                                ms
                              </p>
                            )}
                          {performance.network_time_ms != null &&
                            performance.network_time_ms > 0 && (
                              <p className="text-slate-400">
                                Network:{' '}
                                {performance.network_time_ms.toFixed(2)}ms
                                {performance.network_time_is_heuristic && (
                                  <span className="text-slate-500 ml-1">
                                    (est.)
                                  </span>
                                )}
                              </p>
                            )}
                        </div>
                      )}
                      <p className="text-xs text-slate-500 mt-0.5">
                        Client-side processing (fetch + convert)
                      </p>
                    </div>
                  </div>
                </div>

                {/* CPU Usage */}
                <div className="card">
                  <div className="flex items-center gap-3">
                    <div className="bg-purple-500/20 p-3 rounded-lg">
                      <TrendingUp className="w-6 h-6 text-purple-400" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm text-slate-400">CPU Usage</p>
                      <p className="text-2xl font-bold text-white">
                        {formatCpu(
                          performance.cpu_percent ??
                            performance.cpu_per_core_percent
                        )}
                      </p>
                      {(performance.cpu_raw_percent != null ||
                        performance.cpu_per_core_percent != null ||
                        performance.cpu_seconds_used != null) && (
                        <div className="text-xs text-slate-500 mt-1 space-y-0.5">
                          {performance.cpu_per_core_percent != null && (
                            <p>
                              Per-core:{' '}
                              {performance.cpu_per_core_percent.toFixed(
                                2
                              )}
                              %
                            </p>
                          )}
                          {performance.cpu_raw_percent != null &&
                            (performance.cpu_per_core_percent == null ||
                              performance.cpu_raw_percent >
                                performance.cpu_per_core_percent) && (
                              <p>
                                Raw:{' '}
                                {performance.cpu_raw_percent.toFixed(2)}
                                %
                              </p>
                            )}
                          {performance.cpu_seconds_used != null && (
                            <p>
                              CPU time:{' '}
                              {performance.cpu_seconds_used.toFixed(4)}s
                            </p>
                          )}
                        </div>
                      )}
                      {!performance.cpu_raw_percent &&
                        !performance.cpu_per_core_percent && (
                          <p className="text-xs text-slate-500 mt-1">
                            Measured during execution
                          </p>
                        )}
                      {performance.cpu_timing_source && (
                        <p className="text-xs text-slate-500">
                          Source:{' '}
                          {performance.cpu_timing_source ===
                          'client_process_psutil'
                            ? 'Client psutil (local process)'
                            : performance.cpu_timing_source}
                        </p>
                      )}
                    </div>
                  </div>
                </div>

                {/* Rows Returned */}
                <div className="card">
                  <div className="flex items-center gap-3">
                    <div className="bg-yellow-500/20 p-3 rounded-lg">
                      <Database className="w-6 h-6 text-yellow-400" />
                    </div>
                    <div>
                      <p className="text-sm text-slate-400">Rows Returned</p>
                      <p className="text-2xl font-bold text-white">
                        {formatNumber(performance.row_count)}
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Detailed Timing Breakdown */}
              {(performance.fetch_time_ms != null ||
                performance.network_time_ms != null ||
                performance.wall_elapsed_seconds_median != null ||
                performance.total_time_ms != null ||
                performance.db_execution_time_ms != null ||
                performance.conversion_time_ms != null) && (
                <div className="card">
                  <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                    <Clock className="w-5 h-5 text-blue-400" />
                    Detailed Timing Breakdown
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {performance.db_execution_time_ms != null && (
                      <div className="bg-slate-900 rounded-lg p-3 border border-slate-700">
                        <p className="text-xs text-slate-400 mb-1">
                          Database Execution
                        </p>
                        <p className="text-lg font-bold text-white">
                          {formatMs(performance.db_execution_time_ms)}
                        </p>
                        <p className="text-xs text-slate-500 mt-1">
                          {performance.timing_source === 'database'
                            ? 'From database timing'
                            : 'Client-side timing'}
                        </p>
                        {performance.db_timing_source && (
                          <p className="text-xs text-slate-500">
                            Source:{' '}
                            {performance.db_timing_source ===
                            'explain_analyze'
                              ? 'EXPLAIN ANALYZE'
                              : performance.db_timing_source}
                          </p>
                        )}
                      </div>
                    )}
                    {performance.fetch_time_ms != null && (
                      <div className="bg-slate-900 rounded-lg p-3 border border-slate-700">
                        <p className="text-xs text-slate-400 mb-1">
                          Fetch Time
                        </p>
                        <p className="text-lg font-bold text-white">
                          {formatMs(performance.fetch_time_ms)}
                        </p>
                        <p className="text-xs text-slate-500 mt-1">
                          Time to fetch from database
                        </p>
                      </div>
                    )}
                    {performance.conversion_time_ms != null &&
                      performance.conversion_time_ms > 0 && (
                        <div className="bg-slate-900 rounded-lg p-3 border border-slate-700">
                          <p className="text-xs text-slate-400 mb-1">
                            Conversion Time
                          </p>
                          <p className="text-lg font-bold text-white">
                            {formatMs(performance.conversion_time_ms)}
                          </p>
                          <p className="text-xs text-slate-500 mt-1">
                            Time to convert results
                          </p>
                        </div>
                      )}
                    {performance.network_time_ms != null &&
                      performance.network_time_ms > 0 && (
                        <div className="bg-slate-900 rounded-lg p-3 border border-slate-700">
                          <p className="text-xs text-slate-400 mb-1">
                            Network Time
                          </p>
                          <p className="text-lg font-bold text-white">
                            {formatMs(performance.network_time_ms)}
                          </p>
                          <p className="text-xs text-slate-500 mt-1">
                            {performance.network_time_is_heuristic
                              ? 'Estimated'
                              : 'Measured'}{' '}
                            transfer time
                          </p>
                        </div>
                      )}
                    {performance.wall_elapsed_seconds_median != null && (
                      <div className="bg-slate-900 rounded-lg p-3 border border-slate-700">
                        <p className="text-xs text-slate-400 mb-1">
                          Wall Clock Time (Median)
                        </p>
                        <p className="text-lg font-bold text-white">
                          {formatMs(
                            performance.wall_elapsed_seconds_median * 1000
                          )}
                        </p>
                        <p className="text-xs text-slate-500 mt-1">
                          Total elapsed time
                        </p>
                      </div>
                    )}
                    {performance.total_time_ms != null && (
                      <div className="bg-slate-900 rounded-lg p-3 border border-slate-700">
                        <p className="text-xs text-slate-400 mb-1">
                          Total Time
                        </p>
                        <p className="text-lg font-bold text-green-400">
                          {formatMs(performance.total_time_ms)}
                        </p>
                        <p className="text-xs text-slate-500 mt-1">
                          DB execution + fetch + conversion
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Query Plan */}
              {mode === 'sql' &&
              performance.comparison &&
              performance.comparison.original?.query_plan &&
              performance.comparison.original.query_plan.length > 0 &&
              performance.comparison.optimized?.query_plan &&
              performance.comparison.optimized.query_plan.length > 0 ? (
                // Show both original and optimized plans side by side when comparison exists
                <div className="card">
                  <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                    <Database className="w-5 h-5 text-blue-400" />
                    Query Execution Plans (Original vs Optimized)
                  </h3>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div>
                      <h4 className="text-sm font-semibold text-slate-300 mb-2">
                        Original Query Plan
                      </h4>
                      <QueryPlanViewer
                        plan={performance.comparison.original.query_plan}
                      />
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-slate-300 mb-2">
                        Optimized Query Plan
                      </h4>
                      <QueryPlanViewer
                        plan={performance.comparison.optimized.query_plan}
                      />
                    </div>
                  </div>
                </div>
              ) : (
                performance.query_plan &&
                performance.query_plan.length > 0 && (
                  // Fallback: single plan (natural mode or no comparison)
                  <div className="card">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                      <Database className="w-5 h-5 text-blue-400" />
                      Query Execution Plan
                    </h3>
                    <QueryPlanViewer plan={performance.query_plan} />
                  </div>
                )
              )}

              {/* Query Results Preview */}
              {performance.data &&
                performance.data.length > 0 &&
                performance.columns && (
                  <div className="card">
                    <h3 className="text-lg font-semibold text-white mb-4">
                      Query Results (
                      {formatNumber(performance.row_count)} rows)
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-slate-700">
                            {performance.columns.map((col, idx) => (
                              <th
                                key={idx}
                                className="text-left py-2 px-3 text-slate-400 font-medium"
                              >
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {performance.data.map((row, idx) => (
                            <tr
                              key={idx}
                              className="border-b border-slate-800 hover:bg-slate-800/50"
                            >
                              {performance.columns.map((col, colIdx) => (
                                <td
                                  key={colIdx}
                                  className="py-2 px-3 text-slate-300"
                                >
                                  {row[col] !== null &&
                                  row[col] !== undefined
                                    ? String(row[col])
                                    : 'NULL'}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {(performance.row_count >
                        performance.data.length ||
                        performance.data_truncated) && (
                        <div className="text-sm text-slate-400 mt-3 text-center space-y-1">
                          <p>
                            Showing first {performance.data.length} of{' '}
                            {formatNumber(performance.row_count)} rows
                          </p>
                          {performance.data_truncated && (
                            <p className="text-yellow-400 text-xs">
                              ⚠️ Result set was truncated for display
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}
            </>
          ) : (
            <div className="card">
              <div className="text-center py-8">
                <Clock className="w-12 h-12 text-slate-500 mx-auto mb-4" />
                <p className="text-slate-400">
                  Performance metrics not available
                </p>
                <p className="text-sm text-slate-500 mt-2">
                  The query was not executed or profiling failed
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Suggestions Tab */}
      {activeTab === 'suggestions' && (
        <div className="space-y-6">
          {/* Issues Section */}
          {analysis?.issues && analysis.issues.length > 0 && (
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <AlertTriangle className="w-6 h-6 text-yellow-400" />
                <h3 className="text-xl font-bold text-white">
                  Issues Detected ({analysis.issues.length})
                </h3>
              </div>
              <div className="space-y-3">
                {analysis.issues.map((issue, idx) => (
                  <div
                    key={idx}
                    className={`p-4 rounded-lg border ${
                      issue.severity === 'critical'
                        ? 'bg-red-500/10 border-red-500/30'
                        : issue.severity === 'high'
                        ? 'bg-orange-500/10 border-orange-500/30'
                        : issue.severity === 'medium'
                        ? 'bg-yellow-500/10 border-yellow-500/30'
                        : 'bg-blue-500/10 border-blue-500/30'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <span
                            className={`text-sm font-semibold uppercase ${
                              issue.severity === 'critical'
                                ? 'text-red-400'
                                : issue.severity === 'high'
                                ? 'text-orange-400'
                                : issue.severity === 'medium'
                                ? 'text-yellow-400'
                                : 'text-blue-400'
                            }`}
                          >
                            {issue.severity}
                          </span>
                        </div>
                        <p className="text-white font-medium mb-1">
                          {issue.issue}
                        </p>
                        <p className="text-slate-300 text-sm">
                          {issue.suggestion}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Optimizations Applied Section */}
          {optimizations_applied && optimizations_applied.length > 0 && (
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <Lightbulb className="w-6 h-6 text-green-400" />
                <h3 className="text-xl font-bold text-white">
                  Optimizations Applied ({optimizations_applied.length})
                </h3>
              </div>
              <div className="space-y-2">
                {optimizations_applied.map((opt, idx) => (
                  <div
                    key={idx}
                    className="flex items-start gap-3 p-3 bg-green-500/10 border border-green-500/30 rounded-lg"
                  >
                    <Check className="w-5 h-5 text-green-400 mt-0.5 flex-shrink-0" />
                    <p className="text-slate-300 text-sm">{opt}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* LLM Optimizations Section */}
          {analysis?.llm_optimizations &&
            analysis.llm_optimizations.length > 0 && (
              <div className="card">
                <div className="flex items-center gap-3 mb-4">
                  <Sparkles className="w-6 h-6 text-purple-400" />
                  <h3 className="text-xl font-bold text-white">
                    LLM Optimizations ({analysis.llm_optimizations.length})
                  </h3>
                </div>
                <div className="space-y-2">
                  {analysis.llm_optimizations.map((opt, idx) => (
                    <div
                      key={idx}
                      className="flex items-start gap-3 p-3 bg-purple-500/10 border border-purple-500/30 rounded-lg"
                    >
                      <Sparkles className="w-5 h-5 text-purple-400 mt-0.5 flex-shrink-0" />
                      <p className="text-slate-300 text-sm">{opt}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

          {/* LLM Explanation */}
          {analysis?.llm_explanation && (
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <Lightbulb className="w-6 h-6 text-blue-400" />
                <h3 className="text-xl font-bold text-white">
                  Optimization Explanation
                </h3>
              </div>
              <p className="text-slate-300 whitespace-pre-wrap">
                {analysis.llm_explanation}
              </p>
            </div>
          )}

          {/* General Suggestions */}
          {analysis?.suggestions && analysis.suggestions.length > 0 && (
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <Lightbulb className="w-6 h-6 text-blue-400" />
                <h3 className="text-xl font-bold text-white">
                  Suggestions ({analysis.suggestions.length})
                </h3>
              </div>
              <div className="space-y-2">
                {analysis.suggestions.map((suggestion, idx) => (
                  <div
                    key={idx}
                    className="flex items-start gap-3 p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg"
                  >
                    <Lightbulb className="w-5 h-5 text-blue-400 mt-0.5 flex-shrink-0" />
                    <p className="text-slate-300 text-sm">{suggestion}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Performance Tips */}
          {analysis?.performance_tips &&
            analysis.performance_tips.length > 0 && (
              <div className="card">
                <div className="flex items-center gap-3 mb-4">
                  <TrendingUp className="w-6 h-6 text-cyan-400" />
                  <h3 className="text-xl font-bold text-white">
                    Performance Tips ({analysis.performance_tips.length})
                  </h3>
                </div>
                <div className="space-y-2">
                  {analysis.performance_tips.map((tip, idx) => (
                    <div
                      key={idx}
                      className="flex items-start gap-3 p-3 bg-cyan-500/10 border border-cyan-500/30 rounded-lg"
                    >
                      <TrendingUp className="w-5 h-5 text-cyan-400 mt-0.5 flex-shrink-0" />
                      <p className="text-slate-300 text-sm">{tip}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

          {/* Index Suggestions */}
          {suggested_indexes && suggested_indexes.length > 0 && (
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <Database className="w-6 h-6 text-indigo-400" />
                <h3 className="text-xl font-bold text-white">
                  Index Recommendations ({suggested_indexes.length})
                </h3>
              </div>
              <div className="space-y-3">
                {suggested_indexes.map((index, idx) => {
                  const indexStr =
                    typeof index === 'string'
                      ? index
                      : index.sql_command ||
                        `Index on ${index.table}.${index.column}`
                  return (
                    <div
                      key={idx}
                      className="p-4 bg-indigo-500/10 border border-indigo-500/30 rounded-lg"
                    >
                      <div className="flex items-start gap-3">
                        <Database className="w-5 h-5 text-indigo-400 mt-0.5 flex-shrink-0" />
                        <div className="flex-1">
                          <code className="text-indigo-300 text-sm font-mono block whitespace-pre-wrap">
                            {indexStr}
                          </code>
                          {typeof index === 'object' && index.reason && (
                            <p className="text-slate-400 text-xs mt-2">
                              Reason: {index.reason}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Query Complexity */}
          {analysis?.complexity && (
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <Code className="w-6 h-6 text-slate-400" />
                <h3 className="text-xl font-bold text-white">
                  Query Complexity
                </h3>
              </div>
              <div className="flex items-center gap-3">
                <span
                  className={`px-4 py-2 rounded-lg font-semibold ${
                    analysis.complexity === 'simple'
                      ? 'bg-green-500/20 text-green-400'
                      : analysis.complexity === 'moderate'
                      ? 'bg-yellow-500/20 text-yellow-400'
                      : analysis.complexity === 'complex'
                      ? 'bg-orange-500/20 text-orange-400'
                      : 'bg-red-500/20 text-red-400'
                  }`}
                >
                  {analysis.complexity.toUpperCase()}
                </span>
                <p className="text-slate-400 text-sm">
                  {analysis.complexity === 'simple' &&
                    'Simple query with minimal operations'}
                  {analysis.complexity === 'moderate' &&
                    'Moderate complexity with some joins or aggregations'}
                  {analysis.complexity === 'complex' &&
                    'Complex query with multiple joins and aggregations'}
                  {analysis.complexity === 'very_complex' &&
                    'Very complex query with many nested operations'}
                </p>
              </div>
            </div>
          )}

          {/* Empty State */}
          {(!analysis?.issues ||
            analysis.issues.length === 0) &&
            (!optimizations_applied ||
              optimizations_applied.length === 0) &&
            (!analysis?.suggestions ||
              analysis.suggestions.length === 0) &&
            (!suggested_indexes ||
              suggested_indexes.length === 0) &&
            (!analysis?.performance_tips ||
              analysis.performance_tips.length === 0) && (
              <div className="card">
                <div className="text-center py-8">
                  <Lightbulb className="w-12 h-12 text-slate-500 mx-auto mb-4" />
                  <p className="text-slate-400">
                    No suggestions available
                  </p>
                  <p className="text-sm text-slate-500 mt-2">
                    The query appears to be well-optimized
                  </p>
                </div>
              </div>
            )}
        </div>
      )}
    </div>
  )
}

export default ResultsDashboard
