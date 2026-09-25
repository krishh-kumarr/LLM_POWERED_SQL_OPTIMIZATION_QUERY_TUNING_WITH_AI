# AI SQL Copilot - Complete Platform Guide

## Table of Contents
1. [What is This Platform?](#what-is-this-platform)
2. [Platform Architecture](#platform-architecture)
3. [How Everything Works](#how-everything-works)
4. [Metric Calculations Explained](#metric-calculations-explained)
5. [Complete Feature Breakdown](#complete-feature-breakdown)
6. [Technical Deep Dive](#technical-deep-dive)

---

## What is This Platform?

**AI SQL Copilot** is an intelligent web application that helps you:
- **Generate SQL queries** from natural language (e.g., "Show me all customers who bought products last month")
- **Optimize existing SQL queries** to run faster
- **Analyze query performance** with detailed metrics and visualizations
- **Understand your database schema** automatically

Think of it as a **smart assistant** that sits between you and your database, translating your questions into optimized SQL code.

### Key Capabilities
1. **Natural Language to SQL**: Ask questions in plain English, get SQL code
2. **Query Optimization**: Automatically improve slow queries
3. **Performance Profiling**: See exactly how fast queries run and why
4. **Schema Understanding**: Automatically learns your database structure
5. **Multi-Database Support**: Works with SQLite, MySQL, and PostgreSQL

---

## Platform Architecture

### High-Level Overview

```
┌─────────────────┐
│   Web Browser   │  ← You interact here
│   (React UI)    │
└────────┬────────┘
         │ HTTP Requests
         ▼
┌─────────────────┐
│  Flask Backend  │  ← Handles all logic
│   (Python API)  │
└────────┬────────┘
         │
    ┌────┴────┬──────────────┬─────────────┐
    │         │              │             │
    ▼         ▼              ▼             ▼
┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│Database│ │  Ollama  │ │  Chroma  │ │  psutil  │
│(SQLite │ │   LLM    │ │  Vector  │ │  System  │
│ MySQL  │ │ (Gemma)  │ │   Store  │ │ Metrics  │
│Postgres│ │          │ │          │ │          │
└────────┘ └──────────┘ └──────────┘ └──────────┘
```

### Component Breakdown

#### 1. **Frontend (React + Vite)**
- **Location**: `frontend/src/`
- **Technology**: React 18, Tailwind CSS, Recharts
- **Purpose**: User interface for interacting with the platform
- **Key Components**:
  - `DatabaseConnect.jsx`: Connect to databases
  - `QueryAssistant.jsx`: Input natural language or SQL queries
  - `ResultsDashboard.jsx`: Display results and metrics
  - `SchemaViewer.jsx`: Show database structure

#### 2. **Backend (Flask)**
- **Location**: `backend/`
- **Technology**: Flask, SQLAlchemy, LangChain
- **Purpose**: API server that processes requests
- **Key Files**:
  - `app.py`: Main Flask application
  - `routes/`: API endpoints
  - `services/`: Core business logic
  - `models/`: Database connection handling

#### 3. **AI Components**
- **Ollama (LLM)**: Local language model (Gemma3:4b) for SQL generation
- **Chroma (Vector Store)**: Stores database schema for quick retrieval
- **LangChain**: Orchestrates LLM interactions

#### 4. **Database Layer**
- **SQLAlchemy**: Database abstraction layer
- Supports: SQLite, MySQL, PostgreSQL

---

## How Everything Works

### Step-by-Step Flow

#### **Scenario 1: Natural Language Query**

1. **User Input**
   ```
   User types: "Show me top 5 products by sales"
   ```

2. **Frontend Processing** (`QueryAssistant.jsx`)
   - Validates input
   - Sends POST request to `/api/generate-sql`
   - Shows loading indicator

3. **Backend Receives Request** (`routes/llm_routes.py`)
   - Extracts natural language query
   - Determines database type (SQLite/MySQL/PostgreSQL)

4. **RAG Pipeline Activation** (`services/rag_pipeline.py`)
   - **Step 4a: Schema Retrieval**
     - Queries Chroma vector database for relevant schema information
     - Uses semantic search to find tables/columns related to "products", "sales"
     - Retrieves data dictionary with sample values
   
   - **Step 4b: Context Building**
     - Combines:
       - Strict allowed tables/columns list
       - Relevant schema chunks from vector store
       - Complete data dictionary
       - Sample data values
   
   - **Step 4c: LLM SQL Generation**
     - Sends to Ollama Gemma3:4b:
       ```
       Prompt: "Generate SQL for: Show me top 5 products by sales"
       Schema Context: [retrieved schema information]
       ```
     - LLM generates SQL query
   
   - **Step 4d: Validation & Repair**
     - Validates SQL against actual schema
     - Checks for invalid tables/columns
     - Auto-repairs using column name matching (difflib)
     - If still invalid, asks LLM to repair

5. **Query Optimization** (`services/optimizer_agent.py`)
   - Rule-based analysis:
     - Checks for SELECT *
     - Detects inefficient patterns
     - Suggests indexes
   - LLM-based optimization:
     - Analyzes query structure
     - Suggests improvements

6. **Query Profiling** (`services/sql_profiler.py`)
   - Executes query multiple times (default: 1 time)
   - Measures:
     - Database execution time
     - Fetch time
     - CPU usage
   - Gets query execution plan (EXPLAIN)

7. **Response Assembly**
   - Combines:
     - Generated SQL
     - Performance metrics
     - Optimization suggestions
     - Query plan
     - Sample results

8. **Frontend Display** (`ResultsDashboard.jsx`)
   - Shows SQL query (with copy button)
   - Displays performance charts
   - Shows optimization suggestions
   - Renders query results table

#### **Scenario 2: SQL Query Optimization**

1. **User Input**
   ```
   User pastes SQL: "SELECT * FROM orders WHERE customer_id > 100"
   ```

2. **Backend Processing**
   - Analyzes query for issues
   - Retrieves schema context
   - Generates optimized version:
     ```sql
     SELECT order_id, customer_id, order_date, total_amount 
     FROM orders 
     WHERE customer_id > 100
     ```
   - Profiles both original and optimized queries
   - Compares performance

3. **Results Display**
   - Shows side-by-side comparison
   - Highlights improvements
   - Displays performance metrics

---

## Metric Calculations Explained

### 1. **Database Execution Time** (`db_execution_time_ms`)

**What it measures**: Time spent executing the query on the database server

**How it's calculated**:
- **For PostgreSQL**: Uses `EXPLAIN ANALYZE` which actually executes the query
  ```sql
  EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT ...
  ```
  - Extracts `Execution Time` from JSON response
  - Returns time in milliseconds

- **For MySQL**: Uses `SHOW PROFILES` (if available)
  ```sql
  SET profiling = 1;
  SELECT ...;
  SHOW PROFILES;
  ```
  - Gets execution time from profile
  - Converts seconds to milliseconds

- **For SQLite**: Falls back to client-side timing
  - SQLite doesn't support EXPLAIN ANALYZE
  - Uses Python `time.perf_counter()` measurements

**Source**: `sql_profiler.py` → `_explain_analyze_time()`

**Important Notes**:
- Only measured for read-only queries (SELECT, WITH, EXPLAIN, SHOW)
- For write queries (INSERT, UPDATE, DELETE), this is `None`
- Represents **server-side** execution time, not network time

---

### 2. **Fetch Time** (`fetch_time_ms`)

**What it measures**: Time to transfer results from database to Python client

**How it's calculated**:
```python
fetch_start = time.perf_counter()
# Fetch rows from database cursor
fetch_end = time.perf_counter()
fetch_time_ms = (fetch_end - fetch_start) * 1000.0
```

**Includes**:
- Network transfer time (if remote database)
- Database driver overhead
- Result set serialization

**Source**: `sql_profiler.py` → `profile_query()` → fetch timing section

**Important Notes**:
- Measured on **client side** (Python process)
- Includes network latency for remote databases
- For local SQLite, this is minimal

---

### 3. **Conversion Time** (`conversion_time_ms`)

**What it measures**: Time to convert database rows to Python dictionaries

**How it's calculated**:
```python
conv_start = time.perf_counter()
for row in rows:
    data.append(dict(row._mapping))  # Convert to dict
conv_end = time.perf_counter()
conversion_time_ms = (conv_end - conv_start) * 1000.0
```

**Includes**:
- Converting SQLAlchemy Row objects to dictionaries
- Data type conversions

**Source**: `sql_profiler.py` → `profile_query()` → conversion timing section

---

### 4. **Total Time** (`total_time_ms`)

**What it measures**: Complete end-to-end query execution time

**How it's calculated**:
```python
total_time_ms = db_execution_time_ms + fetch_time_ms + conversion_time_ms
```

**Breakdown**:
- `db_execution_time_ms`: Database server work
- `fetch_time_ms`: Data transfer
- `conversion_time_ms`: Python processing

**Source**: `sql_profiler.py` → `profile_query()` → total time calculation

**Important Notes**:
- If `db_execution_time_ms` is `None`, uses `wall_elapsed_seconds_median * 1000`
- This is the **most important** metric for user experience

---

### 5. **Network Time** (`network_time_ms`)

**What it measures**: Estimated network transfer time (heuristic)

**How it's calculated**:
```python
if db_execution_time_ms is not None:
    network_time_ms = max(0.0, fetch_time_ms - db_execution_time_ms)
```

**Logic**:
- `fetch_time_ms` includes both DB execution and network transfer
- Subtracting `db_execution_time_ms` gives estimated network time
- Clamped to 0 (can't be negative)

**Source**: `sql_profiler.py` → `profile_query()` → network time calculation

**Important Notes**:
- **Heuristic only** - not precise
- Only available when `db_execution_time_ms` is measured
- For local SQLite, this is typically ~0ms

---

### 6. **CPU Usage** (`cpu_percent`, `cpu_raw_percent`, `cpu_per_core_percent`)

**What it measures**: CPU usage during query execution

**How it's calculated**:

**Step 1: Measure CPU time**
```python
cpu_before = process.cpu_times()  # psutil
cpu_before_total = cpu_before.user + cpu_before.system

# Execute query
result = query_func()

cpu_after = process.cpu_times()
cpu_after_total = cpu_after.user + cpu_after.system
cpu_seconds_used = cpu_after_total - cpu_before_total
```

**Step 2: Calculate percentages**
```python
wall_elapsed = time_end - time_start  # Wall clock time
raw_cpu_percent = (cpu_seconds_used / wall_elapsed) * 100.0

# Normalize for multi-core systems
cores = psutil.cpu_count(logical=True)
cpu_per_core_percent = raw_cpu_percent / cores
cpu_per_core_percent = min(100.0, cpu_per_core_percent)  # Cap at 100%
```

**Metrics Explained**:
- `cpu_raw_percent`: Can exceed 100% on multi-core systems (e.g., 200% = 2 cores fully used)
- `cpu_per_core_percent`: Normalized to 0-100% (per-core usage)
- `cpu_percent`: Alias for `cpu_per_core_percent` (for compatibility)
- `cpu_seconds_used`: Total CPU time consumed

**Source**: `sql_profiler.py` → `_measure_cpu_during_execution()`

**Important Notes**:
- Measures **client-side** CPU (Python process)
- Does NOT include database server CPU
- Uses `psutil` library for cross-platform CPU measurement
- Measured over multiple runs (default: 1 run, configurable)

---

### 7. **Wall Clock Time** (`wall_elapsed_seconds_median`)

**What it measures**: Real-world elapsed time (median over multiple runs)

**How it's calculated**:
```python
measurements = []
for _ in range(repeat_count):  # Default: 1
    wall_start = time.perf_counter()
    result = query_func()
    wall_end = time.perf_counter()
    measurements.append(wall_end - wall_start)

# Get median
measurements.sort()
wall_median = measurements[len(measurements) // 2]
```

**Why median?**
- More stable than average
- Filters out outliers (e.g., first-run cold cache effects)

**Source**: `sql_profiler.py` → `profile_query()` → measurement loop

**Important Notes**:
- Includes ALL overhead (DB + network + Python)
- Measured with `time.perf_counter()` (high precision)
- Subtracts instrumentation overhead if measurable

---

### 8. **Query Complexity** (`query_complexity`)

**What it measures**: Estimated complexity level of the query

**How it's calculated**:
```python
complexity_score = 0

# Count JOINs (weight: 2 points each)
complexity_score += query.count('JOIN') * 2

# Count subqueries (weight: 3 points each)
complexity_score += (query.count('SELECT') - 1) * 3

# Count aggregations (weight: 2 points each)
complexity_score += query.count('GROUP BY') * 2
complexity_score += query.count('HAVING') * 2

# Count DISTINCT (weight: 1 point)
complexity_score += query.count('DISTINCT') * 1

# Classify
if complexity_score == 0:
    return 'simple'
elif complexity_score <= 5:
    return 'moderate'
elif complexity_score <= 10:
    return 'complex'
else:
    return 'very_complex'
```

**Source**: `optimizer_agent.py` → `_calculate_complexity()`

**Categories**:
- `simple`: Basic SELECT, no joins or aggregations
- `moderate`: Some joins or aggregations
- `complex`: Multiple joins, subqueries, aggregations
- `very_complex`: Many nested operations

---

### 9. **Query Plan** (`query_plan`)

**What it measures**: Database's execution plan for the query

**How it's retrieved**:

**SQLite**:
```sql
EXPLAIN QUERY PLAN SELECT ...
```
- Returns table format with columns: `id`, `selectid`, `order`, `from`, `detail`

**PostgreSQL**:
```sql
EXPLAIN (FORMAT JSON) SELECT ...
```
- Returns JSON with nested plan structure
- Includes: `Node Type`, `Relation Name`, `Total Cost`, `Plan Rows`, etc.

**MySQL**:
```sql
EXPLAIN FORMAT=JSON SELECT ...
```
- Returns JSON with `query_block` structure
- Includes: `table_name`, `access_type`, `rows_examined`, `cost_info`, etc.

**Source**: `db_connection.py` → `get_query_plan()`

**What it tells us**:
- Which indexes are used
- Full table scans (inefficient)
- Join algorithms (nested loop, hash join, etc.)
- Estimated row counts
- Execution cost

---

### 10. **Performance Improvement** (`time_improvement_percent`)

**What it measures**: Percentage improvement when comparing original vs optimized query

**How it's calculated**:
```python
original_time = original_profile['total_time_ms']
optimized_time = optimized_profile['total_time_ms']

time_improvement_ms = original_time - optimized_time
time_improvement_percent = (time_improvement_ms / original_time) * 100.0
```

**Example**:
- Original: 100ms
- Optimized: 60ms
- Improvement: 40ms (40% faster)

**Source**: `sql_profiler.py` → `compare_queries()`

**Important Notes**:
- Positive = optimized is faster
- Negative = optimized is slower (rare, but possible)

---

### 11. **Index Suggestions** (`suggested_indexes`)

**What it measures**: Recommended database indexes for better performance

**How it's generated**:

**Rule-Based Analysis** (`optimizer_agent.py`):
```python
# Extract columns from WHERE clause
WHERE column_name = value  → Suggest index on column_name

# Extract columns from JOIN conditions
JOIN table ON table.column = other.column  → Suggest indexes on both columns
```

**LLM-Based Suggestions** (`rag_pipeline.py`):
- LLM analyzes query patterns
- Suggests composite indexes for multi-column filters
- Considers query frequency and data distribution

**Source**: `optimizer_agent.py` → `suggest_indexes()`

**Format**:
```python
[
    {
        'table': 'orders',
        'column': 'customer_id',
        'reason': 'Used in WHERE clause',
        'sql_command': 'CREATE INDEX idx_orders_customer_id ON orders(customer_id);'
    }
]
```

---

## Complete Feature Breakdown

### 1. Database Connection

**What it does**: Connects to your database and extracts schema information

**Process**:
1. User provides connection details (host, port, database, credentials).
2. Backend creates a SQLAlchemy engine and tests the connection with a lightweight probe (e.g., `SELECT 1`).
3. Extracts schema using SQLAlchemy’s Inspector:
   - Table names
   - Column names and data types
   - Primary keys and foreign keys
   - Constraints (NULL / NOT NULL / DEFAULT)
4. For each table, fetches a small set of **sample values** for columns (first N rows where possible).
5. Generates a **data dictionary** that captures, for each table/column:
   - Sample values for each column (from the first N rows)
   - Estimated row counts per table
   - Nullability and key information (primary key / foreign key)
6. Builds a relationships summary such as:
   - `orders(customer_id) → customers(customer_id)`
   - `order_items(product_id) → products(product_id)`
7. Stores this structured dictionary and schema text into the vector store so it can be used later by the RAG pipeline and LLM.

**Files**:
- `backend/models/db_connection.py` → `connect()`, `extract_schema()`, `generate_data_dictionary()`
- `backend/routes/db_routes.py` → `/api/connect-db`

---

### 2. Natural Language to SQL Generation

**What it does**: Converts plain English questions into SQL queries

**Process**:
1. **Schema Retrieval** (RAG):
   - Embeds natural query using Sentence Transformers
   - Searches Chroma vector store for relevant schema chunks
   - Retrieves top-k most relevant chunks
   - Includes complete data dictionary

2. **Prompt Construction**:
   ```
   You are an expert SQL query generator.
   
   Schema Context:
   [Retrieved schema with strict allowed tables/columns]
   
   Natural Language Query:
   [User's question]
   
   Generate SQL query...
   ```

3. **LLM Generation**:
   - Sends prompt to Ollama Gemma3:4b
   - LLM generates SQL query
   - Temperature: 0.1 (low for deterministic output)

4. **Validation**:
   - Checks table/column existence
   - Validates alias usage
   - Checks semantic correctness (e.g., "total revenue" → must use SUM)

5. **Auto-Repair**:
   - If validation fails:
     - First: Deterministic repair (column name matching)
     - Then: LLM-based repair with explicit error messages

**Files**:
- `backend/services/rag_pipeline.py` → `generate_sql()`, `generate_optimized_sql()`
- `backend/routes/llm_routes.py` → `/api/generate-sql`

**Example**:
```
Input: "Show me top 5 products by sales"
Output: SELECT p.product_name, SUM(oi.quantity * oi.unit_price) AS total_sales
        FROM products p
        JOIN order_items oi ON p.product_id = oi.product_id
        GROUP BY p.product_id, p.product_name
        ORDER BY total_sales DESC
        LIMIT 5
```

---

### 3. SQL Query Optimization

**What it does**: Improves existing SQL queries for better performance

**Process**:
1. **Rule-Based Analysis**:
   - Detects anti-patterns:
     - `SELECT *` → Suggest specific columns
     - Leading wildcard `LIKE %text` → Prevents index usage
     - Functions on indexed columns → Non-sargable
     - Missing WHERE in UPDATE/DELETE → Critical issue

2. **LLM-Based Optimization**:
   - Analyzes query structure
   - Suggests:
     - Converting subqueries to JOINs
     - Using explicit JOIN syntax
     - Making predicates sargable
     - Removing unnecessary columns/joins

3. **Query Plan Analysis**:
   - Gets EXPLAIN output
   - Identifies:
     - Full table scans
     - Missing indexes
     - Inefficient join algorithms

4. **Performance Comparison**:
   - Profiles original query
   - Profiles optimized query
   - Calculates improvement percentage

**Files**:
- `backend/services/optimizer_agent.py` → `optimize_query_with_llm()`, `comprehensive_optimization()`
- `backend/routes/llm_routes.py` → `/api/optimize-query`

**Example**:
```
Original: SELECT * FROM orders WHERE DATE(order_date) = '2023-01-01'
Optimized: SELECT order_id, customer_id, order_date, total_amount 
           FROM orders 
           WHERE order_date >= '2023-01-01' AND order_date < '2023-01-02'
```

---

### 4. Query Profiling

**What it does**: Measures query performance with detailed metrics

**Metrics Collected**:
- Database execution time
- Fetch time
- Conversion time
- CPU usage
- Query execution plan
- Row count

**Process**:
1. **Read-Only Detection**:
   - Checks if query is SELECT/WITH/EXPLAIN
   - Only safe queries get EXPLAIN ANALYZE

2. **Multiple Runs** (configurable, default: 1):
   - Executes query N times
   - Collects measurements
   - Uses median for stability

3. **CPU Measurement**:
   - Uses `psutil` to measure client CPU
   - Calculates raw and normalized percentages

4. **Query Plan Retrieval**:
   - Gets EXPLAIN output
   - Parses database-specific format

**Files**:
- `backend/services/sql_profiler.py` → `profile_query()`
- `backend/routes/query_routes.py` → `/api/run-query`, `/api/profile-query`

---

### 5. Query Comparison

**What it does**: Compares original vs optimized query performance

**Process**:
1. Profiles original query
2. Profiles optimized query
3. Calculates differences:
   - Time improvement (ms and %)
   - CPU usage comparison
4. Determines if optimized is better:
   - `is_faster`: `time_improvement > 0`

**Files**:
- `backend/services/sql_profiler.py` → `compare_queries()`
- `backend/routes/query_routes.py` → `/api/compare-queries`

---

### 6. Schema Viewer

**What it does**: Displays database schema in a user-friendly format

**Information Shown**:
- Table names
- Column names and types
- Primary keys
- Foreign keys (relationships)
- Sample data

**Files**:
- `frontend/src/components/SchemaViewer.jsx`
- `backend/routes/db_routes.py` → `/api/get-schema`

---

### 7. Results Dashboard

**What it does**: Comprehensive display of query results and metrics

**Sections**:
1. **Overview**:
   - Query summary
   - Performance stats
   - Improvement metrics

2. **SQL Queries**:
   - Generated/optimized SQL
   - Copy-to-clipboard buttons
   - Syntax highlighting

3. **Performance Charts**:
   - Execution time breakdown
   - CPU usage
   - Comparison charts (if optimized)

4. **Query Plan**:
   - Visual execution plan tree
   - Highlights inefficiencies
   - Shows indexes used

5. **Suggestions**:
   - Optimization recommendations
   - Index suggestions
   - Performance tips

**Files**:
- `frontend/src/components/ResultsDashboard.jsx`

---

## Technical Deep Dive

### RAG Pipeline Architecture

**Retrieval-Augmented Generation (RAG)** combines:
1. **Vector Database (Chroma)**: Stores schema information as embeddings
2. **Semantic Search**: Finds relevant schema chunks for queries
3. **LLM (Ollama)**: Generates SQL using retrieved context

**Why RAG?**
- LLMs have limited context windows
- Database schemas can be large
- RAG retrieves only relevant parts
- More accurate SQL generation

**Flow**:
```
Natural Query → Embedding → Vector Search → Schema Chunks → LLM Prompt → SQL
```

**Files**:
- `backend/services/rag_pipeline.py` → `retrieve_relevant_schema()`, `generate_sql()`

---

### Vector Store Indexing

**What gets indexed**:
1. **Schema Chunks**: Split schema text into ~800 character chunks
2. **Complete Schema**: Full schema as JSON
3. **Data Dictionary**: Comprehensive data dictionary with samples

**How it works**:
1. **Text Splitting**: Uses RecursiveCharacterTextSplitter
2. **Embedding**: Sentence Transformers model (`all-MiniLM-L6-v2`)
3. **Storage**: Chroma persistent client
4. **Retrieval**: Semantic similarity search (cosine similarity)

**Files**:
- `backend/services/rag_pipeline.py` → `index_schema()`, `retrieve_relevant_schema()`

---

### Query Validation System

**Multi-Layer Validation**:

1. **Schema Validation**:
   - Checks table existence
   - Checks column existence
   - Validates alias usage
   - Ensures aliases are defined in FROM/JOIN

2. **Semantic Validation**:
   - "Total revenue" → Must use SUM()
   - "Grouped by X" → Must have GROUP BY
   - "Top N" → Must have ORDER BY and LIMIT

3. **Auto-Repair**:
   - **Deterministic**: Column name matching (difflib)
   - **LLM-Based**: Explicit error messages to LLM

**Files**:
- `backend/services/rag_pipeline.py` → `_validate_sql_against_schema()`, `_auto_repair_sql_with_schema()`, `_repair_sql_with_llm()`

---

### Performance Profiling Details

**Measurement Methodology**:

1. **Instrumentation Overhead**:
   - Measures overhead of CPU timing calls
   - Subtracts from wall clock time
   - Ensures accurate measurements

2. **Streaming Support**:
   - For large result sets, streams rows
   - Samples every N rows (default: 10)

3. **Database-Specific Timing**:
   - **PostgreSQL**: EXPLAIN ANALYZE (authoritative)
   - **MySQL**: SHOW PROFILES (best-effort)
   - **SQLite**: Client-side timing (fallback)

**Files**:
- `backend/services/sql_profiler.py` → `profile_query()`, `_measure_cpu_during_execution()`

---

### Optimization Strategies

**Rule-Based Optimizations**:
1. **SELECT * → Specific Columns**: Reduces data transfer
2. **Implicit JOINs → Explicit JOINs**: Better query planner hints
3. **Non-SARGable → SARGable**: Enables index usage
4. **Subqueries → JOINs**: Often faster execution

**LLM-Based Optimizations**:
1. **Query Rewriting**: Structural improvements
2. **Index Recommendations**: Based on query patterns
3. **Join Reordering**: Optimal join order
4. **Predicate Pushdown**: Filters applied early

**Files**:
- `backend/services/optimizer_agent.py` → `optimize_query_with_llm()`, `comprehensive_optimization()`

---

## Understanding the Metrics Dashboard

### Performance Overview Card

**Metrics Shown**:
- **Total Time**: Complete execution time (most important)
- **DB Execution**: Server-side time (if available)
- **Fetch Time**: Network transfer time
- **CPU**: CPU usage percentage

**Color Coding**:
- 🟢 Green: Good performance
- 🟡 Yellow: Moderate performance
- 🔴 Red: Poor performance (needs optimization)

---

### Execution Time Breakdown Chart

**Shows**:
- Database execution time (blue)
- Fetch time (orange)
- Conversion time (green)

**Interpretation**:
- If DB execution is high → Query needs optimization
- If fetch time is high → Network/result size issue
- If conversion time is high → Large result set

---


### Query Plan Visualization

**Shows**:
- Execution plan tree
- Node types (Scan, Join, Sort, etc.)
- Estimated rows
- Cost estimates
- Index usage

**Color Coding**:
- 🔴 Red: Full table scan (inefficient)
- 🟡 Yellow: High cost operation
- 🟢 Green: Efficient operation

---

## Common Use Cases

### Use Case 1: "I want to find all customers who bought products last month"

**What happens**:
1. RAG retrieves schema for `customers`, `orders`, `order_items`, `products`
2. LLM generates SQL with date filtering
3. Query is optimized (removes unnecessary columns)
4. Query is profiled
5. Results show customers with purchase dates

**Generated SQL**:
```sql
SELECT DISTINCT c.customer_id, c.first_name, c.last_name
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
WHERE o.order_date >= DATE('now', '-1 month')
```

---

### Use Case 2: "My query is slow, optimize it"

**What happens**:
1. User pastes slow SQL query
2. System analyzes for issues:
   - Detects SELECT *
   - Finds missing indexes
   - Identifies inefficient patterns
3. Generates optimized version
4. Profiles both queries
5. Shows improvement percentage

**Example**:
- Original: 500ms
- Optimized: 150ms
- Improvement: 70% faster

---

### Use Case 3: "I don't know what queries to run"

**What happens**:
1. System analyzes database schema
2. Generates example queries based on tables
3. User clicks example to load it
4. Query is executed and results shown

**Example Queries Generated**:
- "Show me all customers from the United States"
- "What are the top 5 products by sales?"
- "Calculate total revenue by region"

---

## Troubleshooting Metrics

### Why is `db_execution_time_ms` None?

**Possible reasons**:
1. Query is not read-only (INSERT/UPDATE/DELETE)
2. Database doesn't support EXPLAIN ANALYZE (SQLite)
3. EXPLAIN ANALYZE failed to parse

**Solution**: Check `db_timing_source` field - if `None`, timing is client-side only

---


### Why is CPU usage > 100%?

**This is normal!** `cpu_raw_percent` can exceed 100% on multi-core systems:
- 200% = 2 cores fully utilized
- 400% = 4 cores fully utilized

**Use `cpu_per_core_percent`** for normalized 0-100% values.

---

### Why is network_time_ms negative?

**This shouldn't happen** - it's clamped to 0. If you see negative values, it's a bug.

**Possible cause**: `fetch_time_ms < db_execution_time_ms` (timing inconsistency)

---

## Advanced Configuration

### Profiling Settings

**In `sql_profiler.py`**:
```python
sql_profiler = SQLProfiler(
    repeat=3,  # Number of runs for median
    max_return_rows=1000,  # Max rows in results
    stream_default=False,  # Use streaming mode
)
```

### RAG Settings

**In `.env`**:
```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:4b
VECTOR_STORE_PATH=./vector_store/chroma_index
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

### LLM Temperature

**Lower temperature** (0.1) = More deterministic SQL
**Higher temperature** (0.7) = More creative but less consistent

**Current setting**: 0.1 (for reliable SQL generation)

---

## Conclusion

This platform combines:
- **AI/ML**: LLM for SQL generation, RAG for context retrieval
- **Database Engineering**: Query optimization, performance profiling
- **Web Development**: Modern React UI, Flask API
- **System Monitoring**: CPU and timing metrics

**Key Takeaways**:
1. All metrics are measured client-side (except `db_execution_time_ms`)
2. CPU measurements use `psutil` (cross-platform)
3. Query plans are database-specific (SQLite/MySQL/PostgreSQL)
4. RAG ensures accurate SQL by retrieving relevant schema

**For questions or issues**, check:
- Backend logs: `backend/app.py` console output
- Frontend console: Browser developer tools
- Ollama status: `ollama list` command


