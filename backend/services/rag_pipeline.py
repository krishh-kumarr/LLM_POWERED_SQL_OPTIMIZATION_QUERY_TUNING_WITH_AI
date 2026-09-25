"""
RAG Pipeline Service
====================
Implements Retrieval-Augmented Generation using Ollama and LangChain.
Stores schema information in Chroma vector database for context retrieval.
"""

import os
import logging
from typing import Dict, Optional
import json
import re
import difflib  # for auto-repair of column names

import chromadb
from chromadb.config import Settings
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_community.llms import Ollama
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Import db_connection for schema access (used for validation + example queries)
try:
    from models.db_connection import db_connection
except ImportError:
    db_connection = None
    logger.warning(
        "Could not import db_connection - example query generation and validation may be limited"
    )


class RAGService:
    """Handles RAG pipeline for SQL generation using Ollama and Chroma"""

    def __init__(self):
        logger.info("Initializing RAGService with schema-aware validation")
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "gemma3:4b")
        self.vector_store_path = os.getenv("VECTOR_STORE_PATH", "./vector_store/chroma_index")

        # Initialize Ollama LLM
        try:
            self.llm = Ollama(
                base_url=self.ollama_base_url,
                model=self.ollama_model,
                temperature=0.1,  # Low temperature for more deterministic SQL generation
            )
            logger.info(f"Initialized Ollama with model: {self.ollama_model}")
        except Exception as e:
            logger.error(f"Failed to initialize Ollama: {str(e)}")
            self.llm = None

        # Initialize Chroma vector store
        try:
            self.chroma_client = chromadb.PersistentClient(
                path=self.vector_store_path,
                settings=Settings(anonymized_telemetry=False),
            )
            self.collection = self.chroma_client.get_or_create_collection(
                name="database_schema",
                metadata={"description": "Database schema information for SQL generation"},
            )
            logger.info("Initialized Chroma vector store")
        except Exception as e:
            logger.error(f"Failed to initialize Chroma: {str(e)}")
            self.chroma_client = None
            self.collection = None

        # Initialize embedding model
        try:
            embedding_model = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
            self.embedding_model = SentenceTransformer(embedding_model)
            logger.info(f"Initialized embedding model: {embedding_model}")
        except Exception as e:
            logger.error(f"Failed to initialize embedding model: {str(e)}")
            self.embedding_model = None

        # ---------------------------------------------------------------------
        # PROMPTS (schema-agnostic, only DB-type-specific date syntax)
        # ---------------------------------------------------------------------

        # SQL generation prompt template
        self.sql_generation_prompt = PromptTemplate(
            input_variables=["natural_query", "schema_context", "database_type"],
            template="""
You are an expert SQL query generator specializing in creating highly optimized, production-ready SQL queries.

The schema_context below includes:
- A STRICT ALLOWED TABLES AND COLUMNS list (this is the ONLY schema you are allowed to use)
- Table and column definitions
- Constraints and relationships
- Data dictionary descriptions (column meanings, allowed values, etc.)

Your ABSOLUTE PRIORITIES are:
1) The SQL query MUST exactly match the user's natural language request.
2) The query MUST use ONLY tables and columns that exist in the schema_context.
3) The query MUST be syntactically valid for the target database.

Database Type: {database_type}

Database Schema + Data Dictionary Context:
{schema_context}

Natural Language Query:
{natural_query}

[DATABASE-SPECIFIC DATE/TIME RULES]
Use the CORRECT date/time functions for the given database type.

- For SQLite:
  - "last month"    →  column >= DATE('now','-1 month')
  - "last 7 days"   →  column >= DATE('now','-7 days')
  - "today"         →  column = DATE('now')
  - "before today"  →  column < DATE('now')
  - DO NOT use DATE_SUB, INTERVAL, or PostgreSQL-style intervals in SQLite.

- For MySQL:
  - "last month"    →  column >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH)
  - "last 7 days"   →  column >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
  - "today"         →  column = CURDATE()
  - "before today"  →  column < CURDATE()

- For PostgreSQL:
  - "last month"    →  column >= (CURRENT_DATE - INTERVAL '1 month')
  - "last 7 days"   →  column >= (CURRENT_DATE - INTERVAL '7 days')
  - "today"         →  column = CURRENT_DATE
  - "before today"  →  column < CURRENT_DATE

[CUSTOMER NAME HANDLING RULES]
Look at the schema_context to see how customer names are stored:
- If there are columns like first_name and last_name and NO single "name" column:
  - When the user asks for customer names, use first_name and last_name
    (either separately or concatenated).
- If there is a single "name" column and no first_name/last_name:
  - Use that "name" column for customer names.
- Never reference a name-like column that does not exist in the schema_context.

[SCHEMA ADHERENCE – STRICT, NO MADE-UP COLUMNS]
1. You MUST treat the STRICT ALLOWED TABLES AND COLUMNS list in schema_context as authoritative.
2. You are FORBIDDEN from using any table or column that is not listed there.
3. NEVER invent columns like "total", "revenue", "amount", "id", "name", etc. unless they actually
   appear in the schema_context.
4. When the user asks for "total order value", "largest order", "customer revenue", etc.:
   - First check if an order total column exists (e.g. orders.total, orders.total_amount).
   - If no such column exists, compute the value from existing numeric columns
     (for example: SUM(order_items.quantity * order_items.unit_price)), using only valid columns.
5. Never invent tables or aliases that do not correspond to real tables in the schema context.

[ALIAS & QUALIFICATION RULES]
1. For every table in the FROM / JOIN clauses, define a SHORT alias (e.g. "o" for "orders", "c" for "customers").
2. After defining aliases, ALWAYS reference columns using the alias, NEVER using the bare table name.
   - Example: use "o.order_date", NOT "orders.order_date".
3. NEVER use an alias in SELECT, WHERE, GROUP BY, or ORDER BY that is not defined in the FROM / JOIN clauses.
4. Do NOT invent aliases based on string contents or values (for example, parts of an email like "john" or "example").
5. If you reference a table name like "orders" or "customers", ensure that table is present in FROM/JOIN and has an alias, then use that alias consistently.

[SEMANTIC CORRECTNESS RULES]
1. You MUST strictly follow the natural language request:
   - Do NOT change any filter values from the request.
   - If the user says "United States", you MUST use "United States" in the WHERE clause.
   - If the user asks for "names of customers", you MUST select the customer name-related columns,
     not only IDs.
   - Do NOT add extra filters that change the meaning of the request.

2. Only include JOINs if the natural language query actually needs columns from multiple tables.
   - Example: If the user only wants "names and prices of products in the 'Electronics' category",
     join only the tables needed to identify the category and the products, and do NOT join to
     orders or customers unless explicitly required.

[OPTIMIZATION RULES]
1. Select ONLY the columns required to answer the question (never use SELECT *).
2. Use the minimal set of tables required to answer the question (avoid unnecessary JOINs).
3. Place filtering conditions (WHERE) as early as possible.
4. Use explicit JOIN syntax (INNER JOIN, LEFT JOIN, etc.).
5. Use aggregates and GROUP BY only when the natural query requires aggregation.

Return ONLY the SQL query without any explanations, markdown formatting, or code blocks.
Just the raw SQL query.

SQL Query:
"""
        )

        # Query optimization prompt template (UPDATED)
        self.optimization_prompt = PromptTemplate(
            input_variables=["original_query", "schema_context"],
            template="""
You are an expert MySQL SQL query optimizer.

You are given:
- A STRICT ALLOWED TABLES AND COLUMNS list (this is the ONLY schema you are allowed to use).
- Table and column definitions.
- Relationships and constraints.
- Data dictionary descriptions.

Your job is to:
- Keep the SAME LOGICAL RESULT as the original query.
- Make the query faster, cleaner, and more idiomatic for this schema.
- Strictly respect the schema_context (no invented columns or tables).

================= SCHEMA CONTEXT =================
{schema_context}
==================================================

================= ORIGINAL QUERY =================
{original_query}
==================================================

[STRICT SCHEMA RULES]
1. The STRICT ALLOWED TABLES AND COLUMNS list is authoritative.
2. You are FORBIDDEN from using any table or column that is not in that list.
3. Do NOT invent columns like "total", "revenue", "amount", "id", or "name".
4. Do NOT add joins to tables that are not needed.
5. If the original query uses unnecessary joins, remove those while preserving the result.
6. Do NOT add ORDER BY unless the original query already implies ordering.

[ALIAS & QUALIFICATION RULES]
1. Ensure every alias used in SELECT / WHERE / GROUP BY / ORDER BY is defined in FROM / JOIN.
2. Prefer short, consistent aliases (e.g. "o" for orders, "c" for customers).
3. Once an alias is introduced, always use alias.column, not table.column.
4. Do NOT create aliases from string literals or values (e.g. "john" or "example" from an email).

[REAL OPTIMIZATION PATTERNS – PREFER THESE WHEN SAFE]
Only apply these when they do NOT change the result:

1) Correlated subqueries → JOIN + GROUP BY

   Example pattern to optimize:
   SELECT c.customer_id,
          (SELECT SUM(o.total)
           FROM orders o
           WHERE o.customer_id = c.customer_id) AS total_spent
   FROM customers c;

   Preferred form:
   SELECT c.customer_id,
          SUM(o.total) AS total_spent
   FROM customers c
   JOIN orders o ON o.customer_id = c.customer_id
   GROUP BY c.customer_id;

2) Implicit comma joins → explicit ANSI JOIN

   Replace:
   FROM a, b
   WHERE a.id = b.id

   With:
   FROM a
   JOIN b ON a.id = b.id

3) Non-SARGable predicates → SARGable

   Avoid:
   WHERE DATE(o.order_date) = '2023-01-01'

   Prefer:
   WHERE o.order_date >= '2023-01-01'
     AND o.order_date < '2023-01-02'

4) Remove real redundancy:
   - Drop unused columns from SELECT, GROUP BY, ORDER BY.
   - Drop joins to tables whose columns are never used.
   - Remove unnecessary DISTINCT when GROUP BY already enforces uniqueness.

[WHAT DOES **NOT** COUNT AS A REAL OPTIMIZATION]
These alone are considered **cosmetic only**:
- Just renaming aliases.
- Reformatting / reordering clauses without changing structure.
- Moving columns around in SELECT only.

If you only find cosmetic changes like these, you MUST:
- Return the original query unchanged as "optimized_query".
- Explain that the query was already logically and structurally optimal.

[WHEN THE ORIGINAL QUERY IS ALREADY GOOD]
If the original query:
- Uses proper JOINs,
- Uses appropriate GROUP BY / ORDER BY,
- Uses correct filters and minimal tables,

then:
- Keep the query exactly as-is in "optimized_query".
- Set "optimizations_applied" to:
  ["No optimizations needed. The query is already well-structured and index-friendly."]
- In "explanation", say clearly that the query was already optimal and you did not change its structure.

[OUTPUT FORMAT – STRICT JSON]
Return a single JSON object with EXACTLY these keys:

{{
  "optimized_query": "the optimized SQL query here (or the original if no real optimization is possible)",
  "optimizations_applied": [
    "concrete optimization 1",
    "concrete optimization 2"
  ],
  "explanation": "Short explanation of what you did. If the query was already optimal, say that explicitly."
}}

Rules:
- The JSON must be valid.
- The SQL in "optimized_query" must be valid MySQL and use only schema_context tables/columns.
- If only readability/style changed and no real performance gain is expected, keep the original query as optimized_query and explain that.

Respond with ONLY the JSON object. No markdown, no comments, no backticks.
"""
        )

        # Optimized generation prompt (from natural language)
        self.optimized_generation_prompt = PromptTemplate(
            input_variables=["natural_query", "schema_context", "database_type"],
            template="""
You are an expert SQL query generator specializing in creating highly optimized and CORRECT queries.

The schema_context below includes:
- A STRICT ALLOWED TABLES AND COLUMNS list (this is the ONLY schema you are allowed to use)
- Tables and columns
- Relationships and constraints
- Data dictionary descriptions (what each column means, typical values, etc.)

Your ABSOLUTE PRIORITIES are:
1) The query MUST exactly match the user's natural language request.
2) The query MUST use ONLY tables and columns that exist in the schema_context.
3) The query MUST be syntactically valid for the target database ({database_type}).

Database Type: {database_type}

Database Schema + Data Dictionary Context:
{schema_context}

[DATABASE-SPECIFIC DATE/TIME RULES]
Use the correct date/time functions for the given database type (SQLite, MySQL, PostgreSQL, etc.),
following the patterns in the previous prompt.

[CUSTOMER NAME HANDLING RULES]
Look at the schema_context to see how names are stored:
- If there are columns like first_name and last_name and no single "name" column:
  - Use those for customer names when requested.
- If there is a single "name" column and no first_name/last_name:
  - Use that "name" column.
- Never reference a name-like column that does not exist in the schema.

[SALES / RANKING INTERPRETATION RULES]
When the query asks for:
- "best-selling products", "top products by sales", "most sold products", etc.:
  - Interpret this as products ranked by TOTAL QUANTITY SOLD.
  - Use a join between a product table and an order line / order_items table if such tables exist.
  - Compute total units sold as SUM(quantity_column) from the line items table.
  - GROUP BY the product identifier and product attributes.
  - ORDER BY total_quantity_sold DESC.
  - LIMIT N if the user asks for "top N".

When the query asks for:
- "by revenue", "by total revenue", "by sales amount", "by total sales value":
  - Rank by TOTAL REVENUE:
    • Compute revenue as SUM(quantity * price_column) or SUM(order_total_column),
      using only columns that appear in the schema_context.
    • GROUP BY the dimension requested (product, category, customer, country, etc.).
    • ORDER BY total_revenue DESC.
    • LIMIT N if requested.

When the query asks for:
- "most expensive", "highest price", "cheapest", "lowest price":
  - Use the appropriate price column directly (do not use order line or revenue calculations).
  - ORDER BY price_column DESC for "most expensive"/"highest price".
  - ORDER BY price_column ASC for "cheapest"/"lowest price".
  - LIMIT N if requested.

[SCHEMA ADHERENCE – STRICT, NO MADE-UP COLUMNS]
1. The STRICT ALLOWED TABLES AND COLUMNS list in schema_context is authoritative.
2. You are FORBIDDEN from using any table or column that is not in that list.
3. NEVER reference "total", "revenue", "amount", "id", "name", etc. unless explicitly present
   in the schema_context.
4. For revenue-like queries, prefer existing total columns (e.g. orders.total, orders.total_amount)
   if present; otherwise compute from existing numeric columns.

[ALIAS & QUALIFICATION RULES]
1. For every table in FROM / JOIN, define a clear alias and then use only that alias to qualify columns.
2. Do NOT reference aliases that are not defined in FROM / JOIN.
3. Do NOT invent aliases from parts of string values (such as "john" or "example" from an email).
4. If you use a table name directly (e.g. "orders.total"), ensure that table exists in the schema and appears in FROM/JOIN.

[SEMANTIC CORRECTNESS RULES]
1. Strictly follow the user's request: filters, grouping, ordering.
2. Only include JOINs if necessary for the columns requested.
3. Do NOT add extra conditions that change the meaning.

[OPTIMIZATION RULES]
1. Select ONLY the columns necessary to answer the query (avoid SELECT *).
2. Use the minimal set of tables needed.
3. Use appropriate JOIN conditions (foreign key to primary key).
4. Use GROUP BY only when aggregation is required and only on the correct keys.

[ACTUAL USER QUERY TO ANSWER]
Natural Language Query:
{natural_query}

[OUTPUT FORMAT]
You MUST return a SINGLE JSON object with EXACTLY this shape (no markdown, no extra text):

{{
    "optimized_query": "the optimized SQL query here",
    "optimizations_applied": ["specific optimization 1", "specific optimization 2"],
    "explanation": "Brief explanation of the main optimization and correctness choices you made (including how you avoided using non-existent columns or unnecessary joins).",
    "suggested_indexes": ["index suggestions if applicable, e.g. CREATE INDEX idx_orders_customer_id ON orders(customer_id);"]
}}

Rules for the JSON:
- The JSON must be valid.
- The SQL inside "optimized_query" must be a single complete query.
- Escape double quotes inside the SQL string if needed for valid JSON.

Response:
"""
        )

    # -------------------------------------------------------------------------
    # INTERNAL: STRICT ALLOWED SCHEMA SUMMARY
    # -------------------------------------------------------------------------

    def _build_allowed_schema_summary(self) -> str:
        """
        Build a compact, STRICT list of allowed tables and columns from db_connection.schema_info.

        This is prepended to the RAG context so the LLM sees an explicit whitelist.
        """
        if not db_connection or not getattr(db_connection, "schema_info", None):
            return ""

        schema_info = db_connection.schema_info
        lines = ["=== STRICT ALLOWED TABLES AND COLUMNS ==="]

        for table in schema_info.get("tables", []):
            tname = table.get("name")
            col_names = [c["name"] for c in table.get("columns", [])]
            lines.append(f"TABLE {tname}: {', '.join(col_names)}")

        lines.append("=== END STRICT ALLOWED TABLES AND COLUMNS ===")
        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # SCHEMA + SEMANTIC VALIDATION HELPERS (GENERIC)
    # -------------------------------------------------------------------------

    def _strip_string_literals(self, sql: str) -> str:
        """
        Replace string literals with placeholders so that patterns like
        'john@example.com' are not misinterpreted as alias.column.
        This is ONLY used for validation, not for execution.
        """
        # Remove single-quoted strings: '...'
        sql_no_single = re.sub(r"'([^']|'')*'", "''", sql)
        # Remove double-quoted strings: "..."
        sql_no_strings = re.sub(r'"([^"]|"")*"', '""', sql_no_single)
        return sql_no_strings

    def _validate_sql_against_schema(
        self, sql: str, natural_query: Optional[str] = None
    ) -> Dict:
        """
        Schema + lightweight semantic validator.

        - Uses db_connection.schema_info to check table/column existence.
        - Optionally uses natural_query to enforce simple semantic rules like:
          * "total revenue by X" → must use SUM + GROUP BY + ORDER BY.
          * Queries mentioning countries → must use a country-related column if it exists.
        """
        if not db_connection or not getattr(db_connection, "schema_info", None):
            # Nothing to validate against – assume valid
            return {"valid": True, "errors": []}

        schema_info = db_connection.schema_info
        tables = {t["name"]: t for t in schema_info.get("tables", [])}

        # Collect all column names across the schema for heuristics
        all_columns = set()
        country_columns = []  # (table_name, column_name)
        for t in tables.values():
            for c in t.get("columns", []):
                col_name = c["name"]
                all_columns.add(col_name)
                if "country" in col_name.lower():
                    country_columns.append((t["name"], col_name))

        alias_to_table = {}

        # FROM and JOIN parsing (supports schema prefixes and AS)
        identifier = r"[a-zA-Z_][\w]*"
        table_pattern = rf"(?:{identifier}\.)?{identifier}"  # schema.table or table

        from_re = re.compile(
            rf"\bFROM\s+({table_pattern})(?:\s+(?:AS\s+)?({identifier}))?",
            re.IGNORECASE,
        )
        join_re = re.compile(
            rf"\bJOIN\s+({table_pattern})(?:\s+(?:AS\s+)?({identifier}))?",
            re.IGNORECASE,
        )

        def _base_table_name(full_name: str) -> str:
            # Strip schema prefix: ecommerce.orders -> orders
            if "." in full_name:
                return full_name.split(".")[-1]
            return full_name

        for m in from_re.finditer(sql):
            full_table_name = m.group(1)
            alias = m.group(2)
            table_name = _base_table_name(full_table_name)
            alias_to_table[alias or table_name] = table_name

        for m in join_re.finditer(sql):
            full_table_name = m.group(1)
            alias = m.group(2)
            table_name = _base_table_name(full_table_name)
            alias_to_table[alias or table_name] = table_name

        errors = []

        # --------- TABLE EXISTENCE CHECKS ----------
        for alias, table_name in alias_to_table.items():
            if table_name not in tables:
                errors.append(
                    f"Table '{table_name}' (alias '{alias}') not found in schema. "
                    f"Available tables are: {', '.join(sorted(tables.keys()))}."
                )

        # --------- COLUMN CHECKS ----------
        # IMPORTANT: strip string literals so 'john@example.com' doesn't look like john.example
        sql_for_columns = self._strip_string_literals(sql)

        col_re = re.compile(r"([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*)")
        for m in col_re.finditer(sql_for_columns):
            alias, col = m.group(1), m.group(2)

            # First try alias mapping, then fall back to treating alias as a table name
            table_name = alias_to_table.get(alias)
            if not table_name and alias in tables:
                table_name = alias

            if not table_name:
                errors.append(f"Alias '{alias}' not mapped to any table in FROM/JOIN.")
                continue

            table = tables.get(table_name)
            if not table:
                errors.append(f"Table '{table_name}' (alias '{alias}') not found in schema.")
                continue

            valid_cols = {c["name"] for c in table.get("columns", [])}
            if col not in valid_cols:
                errors.append(
                    f"Column '{alias}.{col}' does not exist. "
                    f"Valid columns for table '{table_name}' are: {', '.join(sorted(valid_cols))}."
                )

        lowered_sql = sql.lower()

        # --------- HEURISTIC: naked "id" only if no such column exists anywhere ----------
        if "id" not in all_columns and re.search(r"\bid\b", lowered_sql):
            pk_candidates = sorted(
                {pk for t in tables.values() for pk in t.get("primary_keys", [])}
            )
            errors.append(
                "Column 'id' is used but no 'id' column exists in the schema. "
                "Use the correct primary key column name(s) instead, such as "
                f"{', '.join(pk_candidates)}."
            )

        # --------- SEMANTIC CHECKS (optional, depends on natural_query) ----------
        if natural_query:
            nq = natural_query.lower()

            # --- Total revenue / sales semantics ---
            asks_total_revenue = any(
                phrase in nq
                for phrase in ["total revenue", "total sales", "sales amount", "sales value"]
            )
            by_group = any(
                phrase in nq for phrase in [" by ", " grouped by", " per ", " each "]
            )

            if asks_total_revenue:
                if "sum(" not in lowered_sql:
                    errors.append(
                        "Natural query asks for total revenue/sales, but SQL does not use SUM() for aggregation."
                    )

                if by_group:
                    if "group by" not in lowered_sql:
                        errors.append(
                            "Natural query asks for totals by a dimension (e.g. category, customer), "
                            "but SQL has no GROUP BY clause."
                        )

                    if "order by" not in lowered_sql and any(
                        phrase in nq for phrase in ["highest", "lowest", "top", "bottom"]
                    ):
                        errors.append(
                            "Natural query asks for results ordered (e.g. from highest to lowest), "
                            "but SQL has no ORDER BY clause."
                        )

            # --- Country semantics (generic, but works nicely for schemas with country columns) ---
            if country_columns:
                mentions_country = any(
                    phrase in nq
                    for phrase in [
                        " country",
                        "countries",
                        "united states",
                        "usa",
                        "canada",
                        "germany",
                        "france",
                        "india",
                        "china",
                        "japan",
                    ]
                )
                if mentions_country and ".country" not in lowered_sql:
                    country_col_list = [f"{t}.{c}" for (t, c) in country_columns]
                    errors.append(
                        "Natural query refers to a country, but SQL does not use any 'country' column. "
                        f"Use one of the schema's country columns instead, such as: {', '.join(country_col_list)}."
                    )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }

    # -------------------------------------------------------------------------
    # AUTO-REPAIR USING AVAILABLE COLUMNS (NO LLM)
    # -------------------------------------------------------------------------

    def _auto_repair_sql_with_schema(self, sql: str, errors: Dict) -> str:
        """
        Best-effort, deterministic repair using ONLY existing columns in the schema.

        - Looks at validation error messages like:
          "Column 'o.total' does not exist. Valid columns for table 'orders' are: order_total, total_amount"
        - Uses difflib.get_close_matches to map wrong columns to the closest valid column.
        - Applies simple textual replacements (alias.wrong_col -> alias.correct_col).

        If no safe replacements are found, returns the original SQL unchanged.
        """
        if (
            not errors
            or not errors.get("errors")
            or not db_connection
            or not getattr(db_connection, "schema_info", None)
        ):
            return sql

        updated_sql = sql
        replacements = []

        # Pattern to extract alias, wrong column, table, and valid columns list
        col_err_re = re.compile(
            r"Column '([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*)' does not exist\. "
            r"Valid columns for table '([a-zA-Z_][\w]*)' are: (.+)\."
        )

        for err in errors["errors"]:
            m = col_err_re.match(err)
            if not m:
                continue

            alias = m.group(1)
            wrong_col = m.group(2)
            table_name = m.group(3)
            valid_cols_str = m.group(4)

            valid_cols = [c.strip() for c in valid_cols_str.split(",") if c.strip()]

            if not valid_cols:
                continue

            # Use difflib to find the closest valid column name
            candidates = difflib.get_close_matches(
                wrong_col, valid_cols, n=1, cutoff=0.6
            )  # cutoff avoids garbage mappings
            if not candidates:
                continue

            best_match = candidates[0]
            if best_match == wrong_col:
                # Somehow identical, nothing to fix
                continue

            logger.info(
                "Auto-repair: mapping column '%s.%s' to '%s.%s' (table '%s')",
                alias,
                wrong_col,
                alias,
                best_match,
                table_name,
            )
            replacements.append((alias, wrong_col, best_match))

        # Apply replacements
        for alias, wrong_col, correct_col in replacements:
            pattern = r"\b" + re.escape(alias) + r"\." + re.escape(wrong_col) + r"\b"
            updated_sql = re.sub(pattern, f"{alias}.{correct_col}", updated_sql)

        return updated_sql

    def _extract_invalid_tables_and_aliases(self, errors: Dict) -> Dict[str, list]:
        """
        From validation errors, extract:
        - invalid table names
        - invalid aliases that don't map to any table

        This is used to explicitly tell the LLM:
        "Do NOT use these tables/aliases again".
        """
        invalid_tables = set()
        invalid_aliases = set()

        if not errors or not errors.get("errors"):
            return {"invalid_tables": [], "invalid_aliases": []}

        for err in errors["errors"]:
            # Example: "Table 'orders' (alias 'o') not found in schema. Available tables are: ..."
            m_table = re.search(
                r"Table '([a-zA-Z_][\w]*)' \(alias '([a-zA-Z_][\w]*)'\) not found in schema",
                err,
            )
            if m_table:
                invalid_tables.add(m_table.group(1))
                invalid_aliases.add(m_table.group(2))
                continue

            # Example: "Alias 'orders' not mapped to any table in FROM/JOIN."
            m_alias = re.search(
                r"Alias '([a-zA-Z_][\w]*)' not mapped to any table in FROM/JOIN", err
            )
            if m_alias:
                invalid_aliases.add(m_alias.group(1))
                continue

        return {
            "invalid_tables": sorted(invalid_tables),
            "invalid_aliases": sorted(invalid_aliases),
        }

    def _repair_sql_with_llm(
        self,
        broken_sql: str,
        schema_context: str,
        errors: Dict,
        natural_query: Optional[str] = None,
    ) -> str:
        """
        Ask the LLM to repair a broken SQL query, given explicit schema + semantic validation errors.
        """
        if not self.llm:
            return broken_sql

        if not errors or not errors.get("errors"):
            return broken_sql

        error_text = "\n".join(errors["errors"])
        nq_text = natural_query or ""

        # extract invalid tables / aliases to forbid
        bad = self._extract_invalid_tables_and_aliases(errors)
        invalid_tables = ", ".join(bad["invalid_tables"]) or "None"
        invalid_aliases = ", ".join(bad["invalid_aliases"]) or "None"

        repair_prompt = PromptTemplate(
            input_variables=[
                "broken_sql",
                "errors",
                "schema_context",
                "natural_query",
                "invalid_tables",
                "invalid_aliases",
            ],
            template="""
You previously generated the following SQL query:

{broken_sql}

However, this query is INVALID for the given schema and/or the user's intent because of these errors:
{errors}

The user's original natural language request was:
{natural_query}

SCHEMA CONTEXT (includes STRICT ALLOWED TABLES AND COLUMNS):
{schema_context}

[FORBIDDEN NAMES]
The following table names do NOT exist in the schema and MUST NOT be used again:
- Invalid tables: {invalid_tables}

The following aliases are invalid (they are not mapped to any table) and MUST NOT be used again:
- Invalid aliases: {invalid_aliases}

Instead, use ONLY the tables and columns that actually appear in the STRICT ALLOWED TABLES AND COLUMNS in the schema_context.

[ALIAS & TABLE REPAIR RULES]
- Every alias that appears in SELECT / WHERE / GROUP BY / ORDER BY MUST correspond to a real table in the FROM / JOIN clauses.
- If an alias was invalid, either:
  • Map it to an existing correct table/alias, OR
  • Remove it and replace with a valid alias.
- Do NOT invent tables or aliases based on string values or email parts (e.g. "john" or "example").
- Use only the real table names from schema_context and give them short, consistent aliases.

Using ONLY the tables and columns that exist in the schema_context below, FIX the SQL query so that:

1. It correctly answers the natural language request.
2. It satisfies all the error messages above.
3. It does NOT invent new tables or columns.
4. It does NOT use any invalid tables or aliases listed above.

Return ONLY the fixed SQL query (no explanations, no markdown).

Fixed SQL:
"""
        )

        chain = LLMChain(llm=self.llm, prompt=repair_prompt)

        repaired = chain.run(
            broken_sql=broken_sql,
            errors=error_text,
            schema_context=schema_context,
            natural_query=nq_text,
            invalid_tables=invalid_tables,
            invalid_aliases=invalid_aliases,
        )

        repaired = repaired.strip()
        if repaired.startswith("```sql"):
            repaired = repaired[6:]
        if repaired.startswith("```"):
            repaired = repaired[3:]
        if repaired.endswith("```"):
            repaired = repaired[:-3]
        repaired = repaired.strip()

        return repaired or broken_sql

    # -------------------------------------------------------------------------
    # INDEXING & RETRIEVAL
    # -------------------------------------------------------------------------

    def index_schema(
        self, schema_text: str, schema_dict: Dict, data_dictionary: Dict = None
    ) -> Dict:
        """
        Index database schema and data dictionary in vector store.

        schema_text: human-readable schema description.
        schema_dict: structured schema JSON.
        data_dictionary: optional structured data dictionary JSON.
        """
        if not self.collection or not self.embedding_model:
            return {
                "success": False,
                "message": "Vector store not initialized",
            }

        try:
            # Clear existing schema documents
            try:
                self.collection.delete(where={"type": "schema"})
                self.collection.delete(where={"type": "complete_schema"})
                self.collection.delete(where={"type": "data_dictionary"})
            except Exception:
                pass  # Collection might be empty

            # Split schema text into chunks
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=800,
                chunk_overlap=100,
                separators=["\n\n", "\n", " ", ""],
            )

            chunks = text_splitter.split_text(schema_text)

            embeddings = self.embedding_model.encode(chunks).tolist()

            ids = [f"schema_chunk_{i}" for i in range(len(chunks))]
            metadatas = [{"type": "schema", "chunk_index": i} for i in range(len(chunks))]

            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=chunks,
                metadatas=metadatas,
            )

            # Store complete schema as JSON
            schema_json = json.dumps(schema_dict, indent=2)
            schema_embedding = self.embedding_model.encode([schema_json]).tolist()

            self.collection.add(
                ids=["complete_schema"],
                embeddings=schema_embedding,
                documents=[schema_json],
                metadatas=[{"type": "complete_schema"}],
            )

            # Store data dictionary if available
            if data_dictionary:
                data_dict_json = json.dumps(data_dictionary, indent=2)
                dict_embedding = self.embedding_model.encode([data_dict_json]).tolist()

                self.collection.add(
                    ids=["data_dictionary"],
                    embeddings=dict_embedding,
                    documents=[data_dict_json],
                    metadatas=[{"type": "data_dictionary"}],
                )
                logger.info("Data dictionary stored in vector database")

            logger.info(f"Indexed {len(chunks)} schema chunks in vector store")

            return {
                "success": True,
                "message": f"Indexed {len(chunks)} schema chunks with data dictionary",
                "chunk_count": len(chunks),
            }

        except Exception as e:
            logger.error(f"Error indexing schema: {str(e)}")
            return {
                "success": False,
                "message": f"Indexing failed: {str(e)}",
            }

    def retrieve_relevant_schema(self, query: str, top_k: int = 5) -> str:
        """
        Retrieve relevant schema context for a natural language query.

        Uses RAG over:
        - schema chunks (type="schema")

        AND always tries to include:
        - full data dictionary doc (id="data_dictionary") if present
        - complete schema JSON (id="complete_schema") if present

        PLUS:
        - A STRICT ALLOWED TABLES AND COLUMNS summary built from db_connection.schema_info.

        All retrieved pieces are concatenated into a single schema_context string.
        """
        if not self.collection or not self.embedding_model:
            # Even if vector store isn't available, we can still provide strict schema
            allowed = self._build_allowed_schema_summary()
            return allowed

        try:
            context_parts = []

            # 1) STRICT ALLOWED SCHEMA SUMMARY (always first)
            allowed = self._build_allowed_schema_summary()
            if allowed:
                context_parts.append(allowed)

            # 2) Retrieve top-k schema chunks
            try:
                query_embedding = self.embedding_model.encode([query]).tolist()[0]
                schema_results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                    where={"type": "schema"},
                )
                schema_docs = schema_results.get("documents", []) if schema_results else []
                if schema_docs and schema_docs[0]:
                    valid_chunks = [doc for doc in schema_docs[0] if doc]
                    if valid_chunks:
                        context_parts.append("\n\n".join(valid_chunks))
                        logger.debug(f"Retrieved {len(valid_chunks)} schema chunks for query.")
            except Exception as e:
                logger.warning(f"Error retrieving schema chunks: {str(e)}")

            # 3) Include data_dictionary doc if stored
            try:
                dd_results = self.collection.get(ids=["data_dictionary"])
                dd_docs = dd_results.get("documents", [])
                if dd_docs and dd_docs[0]:
                    context_parts.append(dd_docs[0])
                    logger.debug("Included data_dictionary document in schema context (direct get).")
            except Exception:
                logger.debug("No data_dictionary context retrieved (may not exist).")

            # 4) Include complete_schema JSON if stored
            try:
                cs_results = self.collection.get(ids=["complete_schema"])
                cs_docs = cs_results.get("documents", [])
                if cs_docs and cs_docs[0]:
                    context_parts.append(cs_docs[0])
                    logger.debug("Included complete_schema document in schema context (direct get).")
            except Exception:
                logger.debug("No complete_schema context retrieved (may not exist).")

            if not context_parts:
                logger.warning("No schema or data dictionary context found in vector store.")
                return allowed or ""

            combined_context = "\n\n".join(context_parts)
            logger.debug("SCHEMA CONTEXT (first 1000 chars):\n%s", combined_context[:1000])
            return combined_context

        except Exception as e:
            logger.error(f"Error retrieving schema context: {str(e)}")
            return self._build_allowed_schema_summary()

    # -------------------------------------------------------------------------
    # GENERATION & OPTIMIZATION
    # -------------------------------------------------------------------------

    def generate_sql(self, natural_query: str, database_type: str = "sqlite") -> Dict:
        """
        Generate SQL query from natural language using RAG + data dictionary.
        Includes post-generation schema + semantic validation and optional repair.

        If validation still fails after repair, returns success=False and validation_errors.
        """
        if not self.llm:
            return {
                "success": False,
                "message": "Ollama LLM not initialized. Please ensure Ollama is running.",
            }

        try:
            schema_context = self.retrieve_relevant_schema(natural_query)

            if not schema_context:
                schema_context = "No schema context available. Generate a generic query."

            chain = LLMChain(llm=self.llm, prompt=self.sql_generation_prompt)

            response = chain.run(
                natural_query=natural_query,
                schema_context=schema_context,
                database_type=database_type,
            )

            generated_sql = response.strip()

            if generated_sql.startswith("```sql"):
                generated_sql = generated_sql[6:]
            if generated_sql.startswith("```"):
                generated_sql = generated_sql[3:]
            if generated_sql.endswith("```"):
                generated_sql = generated_sql[:-3]

            generated_sql = generated_sql.strip()

            # Validate against schema + natural language intent
            validation = self._validate_sql_against_schema(
                generated_sql,
                natural_query=natural_query,
            )

            if not validation["valid"]:
                logger.warning(
                    f"Generated SQL failed schema/semantic validation: {validation['errors']}"
                )

                # FIRST: try deterministic auto-repair using existing columns
                auto_repaired_sql = self._auto_repair_sql_with_schema(
                    generated_sql, validation
                )
                if auto_repaired_sql != generated_sql:
                    auto_validation = self._validate_sql_against_schema(
                        auto_repaired_sql,
                        natural_query=natural_query,
                    )
                    if auto_validation["valid"]:
                        logger.info(
                            "Auto-repaired SQL (using available columns) passed validation."
                        )
                        generated_sql = auto_repaired_sql
                    else:
                        logger.warning(
                            "Auto-repaired SQL still invalid, falling back to LLM repair: "
                            f"{auto_validation['errors']}"
                        )
                        validation = auto_validation  # use latest errors

                # If still invalid after auto-repair (or if no auto-repair happened), use LLM
                if not self._validate_sql_against_schema(
                    generated_sql, natural_query=natural_query
                )["valid"]:
                    repaired_sql = self._repair_sql_with_llm(
                        broken_sql=generated_sql,
                        schema_context=schema_context,
                        errors=validation,
                        natural_query=natural_query,
                    )

                    repaired_validation = self._validate_sql_against_schema(
                        repaired_sql,
                        natural_query=natural_query,
                    )
                    if repaired_validation["valid"]:
                        logger.info("Repaired SQL passed schema/semantic validation.")
                        generated_sql = repaired_sql
                    else:
                        # STILL INVALID → return failure with errors so routes can skip profiling
                        logger.warning(
                            "Repaired SQL still invalid, returning validation errors: "
                            f"{repaired_validation['errors']}"
                        )
                        return {
                            "success": False,
                            "message": "Generated SQL did not pass schema/semantic validation.",
                            "generated_sql": generated_sql,
                            "validation_errors": repaired_validation["errors"],
                            "schema_context_used": (
                                schema_context[:200] + "..."
                                if len(schema_context) > 200
                                else schema_context
                            ),
                        }

            logger.info(f"Generated SQL query for: {natural_query}")

            return {
                "success": True,
                "generated_sql": generated_sql,
                "schema_context_used": (
                    schema_context[:200] + "..." if len(schema_context) > 200 else schema_context
                ),
            }

        except Exception as e:
            logger.error(f"Error generating SQL: {str(e)}")
            return {
                "success": False,
                "message": f"SQL generation failed: {str(e)}",
            }

    def optimize_query(self, original_query: str, schema_context: str = "") -> Dict:
        """
        Optimize an existing SQL query.
        Always uses data dictionary if it's in the vector store (via retrieve_relevant_schema),
        and performs schema validation.

        If validation still fails after repair, returns success=False and validation_errors.
        """
        if not self.llm:
            return {
                "success": False,
                "message": "Ollama LLM not initialized",
            }

        try:
            if not schema_context:
                schema_context = self.retrieve_relevant_schema(original_query)

            chain = LLMChain(llm=self.llm, prompt=self.optimization_prompt)

            response = chain.run(
                original_query=original_query,
                schema_context=schema_context,
            )

            try:
                response = response.strip()
                if response.startswith("```json"):
                    response = response[7:]
                if response.startswith("```"):
                    response = response[3:]
                if response.endswith("```"):
                    response = response[:-3]
                response = response.strip()

                optimization_data = json.loads(response)
                optimized_query = optimization_data.get("optimized_query", original_query)

                # Validate optimized query (schema only)
                validation = self._validate_sql_against_schema(optimized_query)
                if not validation["valid"]:
                    logger.warning(
                        f"Optimized SQL failed schema validation: {validation['errors']}"
                    )

                    # FIRST: deterministic auto-repair using available columns
                    auto_repaired = self._auto_repair_sql_with_schema(
                        optimized_query, validation
                    )
                    if auto_repaired != optimized_query:
                        auto_validation = self._validate_sql_against_schema(auto_repaired)
                        if auto_validation["valid"]:
                            logger.info(
                                "Auto-repaired optimized SQL passed schema validation."
                            )
                            optimized_query = auto_repaired
                        else:
                            logger.warning(
                                "Auto-repaired optimized SQL still invalid, "
                                "falling back to LLM repair: "
                                f"{auto_validation['errors']}"
                            )
                            validation = auto_validation

                    # If still invalid after auto-repair, try LLM repair
                    if not self._validate_sql_against_schema(optimized_query)["valid"]:
                        repaired = self._repair_sql_with_llm(
                            broken_sql=optimized_query,
                            schema_context=schema_context,
                            errors=validation,
                            natural_query=None,
                        )
                        repaired_validation = self._validate_sql_against_schema(repaired)
                        if repaired_validation["valid"]:
                            logger.info(
                                "Repaired optimized SQL (via LLM) passed schema validation."
                            )
                            optimized_query = repaired
                        else:
                            # STILL INVALID → return failure
                            logger.warning(
                                "Repaired optimized SQL still invalid: "
                                f"{repaired_validation['errors']}"
                            )
                            return {
                                "success": False,
                                "message": "Optimized SQL did not pass schema validation.",
                                "optimized_query": optimized_query,
                                "validation_errors": repaired_validation["errors"],
                            }

                return {
                    "success": True,
                    "optimized_query": optimized_query,
                    "optimizations_applied": optimization_data.get(
                        "optimizations_applied", []
                    ),
                    "explanation": optimization_data.get("explanation", ""),
                }
            except json.JSONDecodeError:
                logger.warning("Could not parse optimization response as JSON")
                return {
                    "success": True,
                    "optimized_query": original_query,
                    "optimizations_applied": [],
                    "explanation": response,
                }

        except Exception as e:
            logger.error(f"Error optimizing query: {str(e)}")
            return {
                "success": False,
                "message": f"Query optimization failed: {str(e)}",
            }

    def generate_optimized_sql(
        self, natural_query: str, database_type: str = "sqlite", schema_context: str = ""
    ) -> Dict:
        """
        Generate an optimized SQL query directly from natural language.

        Uses:
        - RAG over schema chunks
        - ALWAYS includes stored data dictionary and complete schema
        - STRICT allowed tables/columns summary
        - Post-generation validation + repair loop

        If validation still fails after repair, returns success=False and validation_errors.
        """
        if not self.llm:
            return {
                "success": False,
                "message": "Ollama LLM not initialized. Please ensure Ollama is running.",
            }

        try:
            if not schema_context:
                schema_context = self.retrieve_relevant_schema(natural_query)

            if not schema_context:
                schema_context = "No schema context available. Generate a generic query."

            chain = LLMChain(llm=self.llm, prompt=self.optimized_generation_prompt)

            response = chain.run(
                natural_query=natural_query,
                schema_context=schema_context,
                database_type=database_type,
            )

            try:
                response = response.strip()
                if response.startswith("```json"):
                    response = response[7:]
                if response.startswith("```"):
                    response = response[3:]
                if response.endswith("```"):
                    response = response[:-3]
                response = response.strip()

                result_data = json.loads(response)

                optimized_query = result_data.get("optimized_query", "")

                # Validate and repair if needed (with natural_query context)
                validation = self._validate_sql_against_schema(
                    optimized_query,
                    natural_query=natural_query,
                )
                if not validation["valid"]:
                    logger.warning(
                        f"Generated optimized SQL failed schema/semantic validation: "
                        f"{validation['errors']}"
                    )

                    # FIRST: deterministic auto-repair using available columns
                    auto_repaired = self._auto_repair_sql_with_schema(
                        optimized_query, validation
                    )
                    if auto_repaired != optimized_query:
                        auto_validation = self._validate_sql_against_schema(
                            auto_repaired,
                            natural_query=natural_query,
                        )
                        if auto_validation["valid"]:
                            logger.info(
                                "Auto-repaired optimized SQL passed schema/semantic validation."
                            )
                            optimized_query = auto_repaired
                        else:
                            logger.warning(
                                "Auto-repaired optimized SQL still invalid, "
                                "falling back to LLM repair: "
                                f"{auto_validation['errors']}"
                            )
                            validation = auto_validation

                    # If still invalid after auto-repair, use LLM
                    if not self._validate_sql_against_schema(
                        optimized_query,
                        natural_query=natural_query,
                    )["valid"]:
                        repaired = self._repair_sql_with_llm(
                            broken_sql=optimized_query,
                            schema_context=schema_context,
                            errors=validation,
                            natural_query=natural_query,
                        )
                        repaired_validation = self._validate_sql_against_schema(
                            repaired,
                            natural_query=natural_query,
                        )
                        if repaired_validation["valid"]:
                            logger.info(
                                "Repaired optimized SQL passed schema/semantic validation."
                            )
                            optimized_query = repaired
                        else:
                            # STILL INVALID → return failure with validation errors
                            logger.warning(
                                "Repaired optimized SQL still invalid: "
                                f"{repaired_validation['errors']}"
                            )
                            return {
                                "success": False,
                                "message": "Generated optimized SQL did not pass schema/semantic validation.",
                                "optimized_query": optimized_query,
                                "validation_errors": repaired_validation["errors"],
                                "optimizations_applied": result_data.get(
                                    "optimizations_applied", []
                                ),
                                "explanation": result_data.get("explanation", ""),
                                "suggested_indexes": result_data.get(
                                    "suggested_indexes", []
                                ),
                            }

                logger.info(f"Generated optimized SQL query for: {natural_query}")

                return {
                    "success": True,
                    "optimized_query": optimized_query,
                    "optimizations_applied": result_data.get("optimizations_applied", []),
                    "explanation": result_data.get("explanation", ""),
                    "suggested_indexes": result_data.get("suggested_indexes", []),
                }
            except json.JSONDecodeError:
                logger.warning("Could not parse response as JSON, extracting SQL")
                sql_query = response.strip()

                if sql_query.startswith("```sql"):
                    sql_query = sql_query[6:]
                if sql_query.startswith("```"):
                    sql_query = sql_query[3:]
                if sql_query.endswith("```"):
                    sql_query = sql_query[:-3]
                sql_query = sql_query.strip()

                # Validate and possibly repair
                validation = self._validate_sql_against_schema(
                    sql_query,
                    natural_query=natural_query,
                )
                if not validation["valid"]:
                    logger.warning(
                        f"Fallback optimized SQL failed schema/semantic validation: "
                        f"{validation['errors']}"
                    )

                    # FIRST: deterministic auto-repair
                    auto_repaired = self._auto_repair_sql_with_schema(
                        sql_query, validation
                    )
                    if auto_repaired != sql_query:
                        auto_validation = self._validate_sql_against_schema(
                            auto_repaired,
                            natural_query=natural_query,
                        )
                        if auto_validation["valid"]:
                            logger.info(
                                "Repaired fallback optimized SQL passed schema/semantic validation."
                            )
                            sql_query = auto_repaired
                        else:
                            logger.warning(
                                "Auto-repaired fallback optimized SQL still invalid, "
                                "falling back to LLM repair: "
                                f"{auto_validation['errors']}"
                            )
                            validation = auto_validation

                    if not self._validate_sql_against_schema(
                        sql_query,
                        natural_query=natural_query,
                    )["valid"]:
                        repaired = self._repair_sql_with_llm(
                            broken_sql=sql_query,
                            schema_context=schema_context,
                            errors=validation,
                            natural_query=natural_query,
                        )
                        repaired_validation = self._validate_sql_against_schema(
                            repaired,
                            natural_query=natural_query,
                        )
                        if repaired_validation["valid"]:
                            logger.info(
                                "Repaired fallback optimized SQL passed schema/semantic validation."
                            )
                            sql_query = repaired
                        else:
                            # STILL INVALID → return failure
                            logger.warning(
                                "Repaired fallback optimized SQL still invalid: "
                                f"{repaired_validation['errors']}"
                            )
                            return {
                                "success": False,
                                "message": "Generated optimized SQL did not pass schema/semantic validation (fallback path).",
                                "optimized_query": sql_query,
                                "validation_errors": repaired_validation["errors"],
                                "optimizations_applied": ["Direct optimization applied"],
                                "explanation": "Query generated with strict semantic and schema adherence rules, but could not be fully validated.",
                                "suggested_indexes": [],
                            }

                logger.info(f"Generated optimized SQL (fallback) for: {natural_query}")

                return {
                    "success": True,
                    "optimized_query": sql_query,
                    "optimizations_applied": ["Direct optimization applied"],
                    "explanation": "Query generated with strict semantic and schema adherence rules",
                    "suggested_indexes": [],
                }

        except Exception as e:
            logger.error(f"Error generating optimized SQL: {str(e)}")
            return {
                "success": False,
                "message": f"Optimized SQL generation failed: {str(e)}",
            }

    def generate_example_queries(self, count: int = 5) -> Dict:
        """
        Generate example natural language queries based on the database schema.
        This still prefers db_connection.schema_info if available.
        """
        if not self.llm:
            return {
                "success": False,
                "message": "Ollama LLM not initialized. Please ensure Ollama is running.",
            }

        try:
            schema_context = ""
            try:
                if db_connection and getattr(db_connection, "schema_info", None):
                    schema_context = db_connection.generate_schema_text()
            except Exception as e:
                logger.warning(f"Could not get schema context: {str(e)}")

            if not schema_context:
                if db_connection and getattr(db_connection, "schema_info", None):
                    tables = db_connection.schema_info.get("tables", [])
                    table_names = [t["name"] for t in tables]
                    schema_context = (
                        f"Database has {len(table_names)} tables: {', '.join(table_names)}"
                    )
                else:
                    schema_context = "No schema information available"

            example_queries_prompt = PromptTemplate(
                input_variables=["schema_context", "count"],
                template="""
You are an expert at creating natural language queries for SQL databases.

Database Schema + Data Dictionary:
{schema_context}

Generate exactly {count} diverse, realistic natural language queries that would be useful for this database.
The queries should:
1. Use actual table and column names from the schema above.
2. Be practical and useful (not generic).
3. Cover different types of queries (SELECT, aggregations, joins, filters, etc.).
4. Be written in natural, conversational language.
5. Be specific to the data in this database.

Return ONLY a JSON array of strings, one query per string. No markdown, no explanation, just the array.

Example format:
["Show me all customers from the United States", "What are the top 5 products by sales?", "Calculate total revenue by country"]

Response:
"""
            )

            chain = LLMChain(llm=self.llm, prompt=example_queries_prompt)

            response = chain.run(
                schema_context=schema_context,
                count=count,
            )

            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            try:
                queries = json.loads(response)
                if isinstance(queries, list):
                    queries = [str(q).strip() for q in queries[:count] if q]
                    logger.info(f"Generated {len(queries)} example queries based on schema")
                    return {
                        "success": True,
                        "example_queries": queries,
                    }
                else:
                    raise ValueError("Response is not a list")
            except (json.JSONDecodeError, ValueError):
                logger.warning("Could not parse example queries as JSON")
                queries = re.findall(r'"([^"]+)"', response)
                if queries:
                    queries = queries[:count]
                    return {
                        "success": True,
                        "example_queries": queries,
                    }
                else:
                    return {
                        "success": True,
                        "example_queries": [
                            "Show me all records from the first table",
                            "What are the top 5 items?",
                            "Calculate totals by category or country",
                            "Find records matching a condition",
                            "Show summary statistics",
                        ],
                    }

        except Exception as e:
            logger.error(f"Error generating example queries: {str(e)}")
            return {
                "success": True,
                "example_queries": [
                    "Show me all records from the first table",
                    "What are the top 5 items?",
                    "Calculate totals by category or country",
                    "Find records matching a condition",
                    "Show summary statistics",
                ],
            }


# Global RAG service instance
rag_service = RAGService()
