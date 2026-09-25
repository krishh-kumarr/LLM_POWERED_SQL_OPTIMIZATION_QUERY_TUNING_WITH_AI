"""
SQL Optimizer Agent
===================
Advanced SQL query analyzer and optimizer with intelligent interpretation.
Uses rule-based analysis, query plan parsing, and LLM-powered recommendations.
"""

import re
import logging
import json
import os
from typing import Dict, List, Any, Optional

from services.rag_pipeline import rag_service
from models.db_connection import db_connection

from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_community.llms import Ollama

logger = logging.getLogger(__name__)


class OptimizerAgent:
    """Analyzes and optimizes SQL queries"""
    
    def __init__(self):
        # Common SQL anti-patterns and optimization rules
        self.optimization_rules = [
            {
                'pattern': r'SELECT\s+\*',
                'issue': 'Using SELECT * instead of specific columns',
                'suggestion': 'Specify only required columns to reduce data transfer and memory usage',
                'severity': 'medium'
            },
            {
                'pattern': r'WHERE.*LIKE\s+[\'"]%',
                'issue': 'Leading wildcard in LIKE clause',
                'suggestion': 'Avoid leading wildcards (LIKE %text) as they prevent index usage',
                'severity': 'high'
            },
            {
                'pattern': r'OR',
                'issue': 'Multiple OR conditions',
                'suggestion': 'Consider using IN clause or UNION for better performance',
                'severity': 'low'
            },
            {
                'pattern': r'WHERE.*\+|\-|\*|/',
                'issue': 'Function or operation on indexed column in WHERE',
                'suggestion': 'Avoid functions/operations on indexed columns in WHERE clause',
                'severity': 'high'
            },
            {
                'pattern': r'(?i)NOT\s+IN',
                'issue': 'Using NOT IN',
                'suggestion': 'Consider using NOT EXISTS or LEFT JOIN for better performance',
                'severity': 'medium'
            },
            {
                'pattern': r'(?i)DISTINCT',
                'issue': 'Using DISTINCT',
                'suggestion': 'DISTINCT can be expensive. Consider if it\'s necessary or use GROUP BY',
                'severity': 'low'
            }
        ]

        # Attach logger
        self.logger = logger

        # Initialize LLM (Ollama) for deep diagnosis
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "gemma3:4b")
        try:
            self.llm = Ollama(
                base_url=self.ollama_base_url,
                model=self.ollama_model,
                temperature=0.1,
            )
            self.logger.info(f"OptimizerAgent using LLM model: {self.ollama_model}")
        except Exception as e:
            self.logger.error(f"Failed to init OptimizerAgent LLM: {e}")
            self.llm = None
    
    def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        Analyze SQL query for potential issues
        
        Args:
            query (str): SQL query to analyze
        
        Returns:
            dict: Analysis results with issues and suggestions
        """
        try:
            query_upper = query.upper()
            issues_found = []
            suggestions = []
            
            # Check for common anti-patterns
            for rule in self.optimization_rules:
                if re.search(rule['pattern'], query, re.IGNORECASE):
                    issues_found.append({
                        'issue': rule['issue'],
                        'suggestion': rule['suggestion'],
                        'severity': rule['severity']
                    })
                    suggestions.append(rule['suggestion'])
            
            # Additional checks
            
            # Check for missing JOIN conditions
            if 'FROM' in query_upper and ',' in query:
                from_clause = (
                    query_upper.split('FROM')[1].split('WHERE')[0]
                    if 'WHERE' in query_upper
                    else query_upper.split('FROM')[1]
                )
                if ',' in from_clause and 'JOIN' not in from_clause:
                    issues_found.append({
                        'issue': 'Implicit JOIN (comma-separated tables)',
                        'suggestion': 'Use explicit JOIN syntax (INNER JOIN, LEFT JOIN) for clarity',
                        'severity': 'medium'
                    })
                    suggestions.append('Use explicit JOIN syntax')
            
            # Check for missing WHERE clause in UPDATE/DELETE
            if ('UPDATE' in query_upper or 'DELETE' in query_upper) and 'WHERE' not in query_upper:
                issues_found.append({
                    'issue': 'UPDATE/DELETE without WHERE clause',
                    'suggestion': 'Always use WHERE clause with UPDATE/DELETE to avoid unintended changes',
                    'severity': 'critical'
                })
                suggestions.append('Add WHERE clause to UPDATE/DELETE')
            
            # Check for subqueries that could be JOINs
            if query.count('SELECT') > 1 and 'WHERE' in query_upper:
                issues_found.append({
                    'issue': 'Subquery in WHERE clause',
                    'suggestion': 'Consider converting subquery to JOIN for better performance',
                    'severity': 'medium'
                })
                suggestions.append('Convert subquery to JOIN')
            
            # Performance insights
            performance_tips = self._generate_performance_tips(query)
            
            return {
                'success': True,
                'issues_count': len(issues_found),
                'issues': issues_found,
                'suggestions': suggestions,
                'performance_tips': performance_tips,
                'query_complexity': self._calculate_complexity(query)
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing query: {str(e)}")
            return {
                'success': False,
                'message': f'Query analysis failed: {str(e)}'
            }
    
    def _calculate_complexity(self, query: str) -> str:
        """Calculate query complexity based on various factors"""
        query_upper = query.upper()
        complexity_score = 0
        
        # Count JOINs
        complexity_score += query_upper.count('JOIN') * 2
        
        # Count subqueries
        complexity_score += (query.count('SELECT') - 1) * 3
        
        # Count aggregations
        complexity_score += query_upper.count('GROUP BY') * 2
        complexity_score += query_upper.count('HAVING') * 2
        
        # Count DISTINCT
        complexity_score += query_upper.count('DISTINCT') * 1
        
        # Determine complexity level
        if complexity_score == 0:
            return 'simple'
        elif complexity_score <= 5:
            return 'moderate'
        elif complexity_score <= 10:
            return 'complex'
        else:
            return 'very_complex'
    
    def _generate_performance_tips(self, query: str) -> List[str]:
        """Generate general performance tips based on query structure"""
        tips = []
        query_upper = query.upper()
        
        if 'JOIN' in query_upper:
            tips.append('Ensure JOIN columns are indexed for optimal performance')
        
        if 'WHERE' in query_upper:
            tips.append('Index columns used in WHERE clause for faster filtering')
        
        if 'GROUP BY' in query_upper:
            tips.append('Consider indexing GROUP BY columns to speed up aggregations')
        
        if 'ORDER BY' in query_upper:
            tips.append('Indexing ORDER BY columns can improve sorting performance')
        
        if 'LIMIT' not in query_upper and 'TOP' not in query_upper:
            tips.append('Consider adding LIMIT clause if you don\'t need all results')
        
        return tips
    
    def suggest_indexes(self, query: str, schema_info: Dict = None) -> List[Dict[str, str]]:
        """
        Suggest indexes based on query patterns
        
        Args:
            query (str): SQL query to analyze
            schema_info (dict): Database schema information
        
        Returns:
            list: Suggested indexes with table and column information
        """
        suggestions = []
        query_upper = query.upper()
        
        try:
            # Extract table and column names from WHERE clause
            if 'WHERE' in query_upper:
                where_match = re.search(
                    r'WHERE\s+(.+?)(?:GROUP BY|ORDER BY|LIMIT|$)',
                    query,
                    re.IGNORECASE | re.DOTALL
                )
                if where_match:
                    where_clause = where_match.group(1)
                    
                    # Find column references
                    column_pattern = r'(\w+)\.(\w+)|(\w+)\s*[=<>!]'
                    matches = re.findall(column_pattern, where_clause)
                    
                    for match in matches:
                        if match[0] and match[1]:  # table.column format
                            suggestions.append({
                                'table': match[0],
                                'column': match[1],
                                'reason': 'Used in WHERE clause'
                            })
                        elif match[2]:  # column only
                            suggestions.append({
                                'table': 'unknown',
                                'column': match[2],
                                'reason': 'Used in WHERE clause'
                            })
            
            # Extract columns from JOIN conditions
            join_pattern = (
                r'JOIN\s+(\w+)\s+(?:AS\s+)?(\w+)?\s+ON\s+'
                r'(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)'
            )
            join_matches = re.findall(join_pattern, query, re.IGNORECASE)
            
            for match in join_matches:
                suggestions.append({
                    'table': match[2] if match[2] else match[0],
                    'column': match[3],
                    'reason': 'Used in JOIN condition'
                })
                suggestions.append({
                    'table': match[4],
                    'column': match[5],
                    'reason': 'Used in JOIN condition'
                })
            
            # Remove duplicates
            unique_suggestions = []
            seen = set()
            for sugg in suggestions:
                key = f"{sugg['table']}.{sugg['column']}"
                if key not in seen:
                    seen.add(key)
                    unique_suggestions.append(sugg)
            
            return unique_suggestions
            
        except Exception as e:
            self.logger.error(f"Error suggesting indexes: {str(e)}")
            return []
    
    def optimize_query_with_llm(self, query: str, schema_context: str = "") -> Dict[str, Any]:
        """
        Use LLM to optimize query
        
        Args:
            query (str): SQL query to optimize
            schema_context (str): Database schema context
        
        Returns:
            dict: Optimization results from LLM
        """
        try:
            # Get rule-based analysis first
            analysis = self.analyze_query(query)
            
            # Get LLM-powered optimization
            llm_result = rag_service.optimize_query(query, schema_context)
            
            if not llm_result['success']:
                return {
                    'success': False,
                    'message': llm_result.get('message', 'LLM optimization failed'),
                    'rule_based_analysis': analysis
                }
            
            # Combine rule-based and LLM suggestions
            all_suggestions = list(set(
                analysis.get('suggestions', []) + 
                llm_result.get('optimizations_applied', [])
            ))
            
            return {
                'success': True,
                'original_query': query,
                'optimized_query': llm_result.get('optimized_query', query),
                'rule_based_issues': analysis.get('issues', []),
                'llm_optimizations': llm_result.get('optimizations_applied', []),
                'all_suggestions': all_suggestions,
                'explanation': llm_result.get('explanation', ''),
                'query_complexity': analysis.get('query_complexity', 'unknown'),
                'suggested_indexes': self.suggest_indexes(query)
            }
            
        except Exception as e:
            self.logger.error(f"Error in LLM optimization: {str(e)}")
            return {
                'success': False,
                'message': f'Optimization failed: {str(e)}'
            }
    
    def interpret_query_plan(self, query_plan: List[Dict]) -> Dict[str, Any]:
        """
        Intelligently interpret EXPLAIN query plan output
        
        Args:
            query_plan: Raw query plan from database EXPLAIN
        
        Returns:
            dict: Human-readable interpretation with insights
        """
        if not query_plan:
            return {
                'summary': 'No query plan available',
                'operations': [],
                'inefficiencies': [],
                'cost_estimate': 'unknown',
                'recommendations': []
            }
        
        interpretation = {
            'summary': '',
            'operations': [],
            'inefficiencies': [],
            'recommendations': []
        }
        
        # Parse operations from plan
        for step in query_plan:
            operation = {
                'type': '',
                'description': '',
                'cost_impact': 'low'
            }
            
            step_str = str(step).lower()
            
            # Identify operation types
            if 'seq scan' in step_str or 'sequential scan' in step_str:
                operation['type'] = 'Sequential Scan'
                operation['description'] = 'Full table scan - reading all rows'
                operation['cost_impact'] = 'high'
                interpretation['inefficiencies'].append(
                    'Sequential scan detected - consider adding an index'
                )
            elif 'index scan' in step_str:
                operation['type'] = 'Index Scan'
                operation['description'] = 'Using index for efficient lookup'
                operation['cost_impact'] = 'low'
            elif 'nested loop' in step_str:
                operation['type'] = 'Nested Loop Join'
                operation['description'] = 'Joining tables with nested iterations'
                if 'large' in step_str:
                    operation['cost_impact'] = 'high'
                    interpretation['inefficiencies'].append(
                        'Nested loop on large dataset - consider hash join or merge join'
                    )
            elif 'hash join' in step_str:
                operation['type'] = 'Hash Join'
                operation['description'] = 'Efficient join using hash table'
                operation['cost_impact'] = 'medium'
            elif 'sort' in step_str:
                operation['type'] = 'Sort'
                operation['description'] = 'Sorting results'
                operation['cost_impact'] = 'medium'
                
            interpretation['operations'].append(operation)
        
        # Generate summary
        high_cost_ops = [op for op in interpretation['operations'] if op['cost_impact'] == 'high']
        if high_cost_ops:
            interpretation['summary'] = (
                f"Query has {len(high_cost_ops)} high-cost operation(s). "
            )
        else:
            interpretation['summary'] = "Query execution plan looks efficient. "
        
        interpretation['summary'] += f"Total operations: {len(interpretation['operations'])}"
        
        # Generate recommendations
        if interpretation['inefficiencies']:
            interpretation['recommendations'] = [
                'Add indexes on columns used in WHERE and JOIN conditions',
                'Consider query rewriting to avoid sequential scans',
                'Analyze table statistics for better query planning'
            ]
        else:
            interpretation['recommendations'] = []
        
        return interpretation
    
    def comprehensive_optimization(
        self, 
        original_query: str, 
        schema_context: str = "",
        execution_time_original: float = None
    ) -> Dict[str, Any]:
        """
        Perform comprehensive query optimization with full analysis
        
        Args:
            original_query: Original SQL query
            schema_context: Database schema information
            execution_time_original: Optional original execution time
        
        Returns:
            dict: Structured JSON output with complete analysis
        """
        try:
            # Step 1: Analyze original query
            self.logger.info("Step 1: Analyzing original query...")
            analysis = self.analyze_query(original_query)
            
            # Step 2: Get query plan interpretation (best-effort, safe)
            self.logger.info("Step 2: Interpreting query execution plan...")
            plan_result = None
            try:
                if db_connection and hasattr(db_connection, "get_query_plan"):
                    plan_result = db_connection.get_query_plan(original_query)
            except Exception as e:
                self.logger.warning(f"get_query_plan failed in comprehensive_optimization: {e}")
                plan_result = None

            raw_plan = []
            if isinstance(plan_result, dict) and plan_result.get("success"):
                raw_plan = plan_result.get("plan", []) or []

            plan_interpretation = self.interpret_query_plan(raw_plan)
            
            # Step 3: Generate optimized query using LLM
            self.logger.info("Step 3: Generating optimized query...")
            llm_result = rag_service.optimize_query(original_query, schema_context)
            
            if not llm_result.get('success', False):
                optimized_query = original_query
                optimizations_applied = []
                explanation = "Failed to generate optimization"
            else:
                optimized_query = llm_result.get('optimized_query', original_query)
                optimizations_applied = llm_result.get('optimizations_applied', [])
                explanation = llm_result.get('explanation', '')
            
            # Step 4: Suggest indexes
            self.logger.info("Step 4: Generating index recommendations...")
            index_suggestions = self.suggest_indexes(original_query)
            
            # Step 5: Compile comprehensive result
            result = {
                'success': True,
                'query_analysis': {
                    'original_query': original_query,
                    'summary': self._generate_query_summary(original_query, analysis),
                    'complexity': analysis.get('query_complexity', 'unknown'),
                    'issues_found': len(analysis.get('issues', [])),
                    'issues': analysis.get('issues', []),
                    'query_plan_interpretation': plan_interpretation
                },
                'optimized_query': optimized_query,
                'optimization_details': {
                    'techniques_applied': optimizations_applied,
                    'rule_based_suggestions': analysis.get('suggestions', []),
                    'performance_tips': analysis.get('performance_tips', [])
                },
                'optimization_explanation': explanation,
                'index_recommendations': [
                    {
                        'table': idx['table'],
                        'column': idx['column'],
                        'reason': idx['reason'],
                        'sql_command': (
                            f"CREATE INDEX idx_{idx['table']}_{idx['column']} "
                            f"ON {idx['table']}({idx['column']});"
                        )
                    }
                    for idx in index_suggestions
                ],
                'performance_comparison': {
                    'original_time': execution_time_original if execution_time_original else 'not measured',
                    'estimated_improvement': self._estimate_improvement(analysis, optimizations_applied)
                },
                'suggestions': self._generate_actionable_suggestions(
                    analysis, plan_interpretation, index_suggestions
                )
            }
            
            self.logger.info("Comprehensive optimization completed successfully")
            return result
            
        except Exception as e:
            self.logger.error(f"Error in comprehensive optimization: {str(e)}")
            return {
                'success': False,
                'message': f'Comprehensive optimization failed: {str(e)}',
                'original_query': original_query
            }
    
    def _generate_query_summary(self, query: str, analysis: Dict) -> str:
        """Generate natural language summary of what the query does"""
        query_upper = query.upper()
        
        summary_parts = []
        
        # Determine main operation
        if 'SELECT' in query_upper:
            if 'JOIN' in query_upper:
                join_count = query_upper.count('JOIN')
                summary_parts.append(f"Retrieves data by joining {join_count + 1} table(s)")
            else:
                summary_parts.append("Retrieves data from a single table")
        
        if 'WHERE' in query_upper:
            summary_parts.append("with filtering conditions")
        
        if 'GROUP BY' in query_upper:
            summary_parts.append("and aggregates results by grouping")
        
        if 'ORDER BY' in query_upper:
            summary_parts.append("sorted by specified columns")
        
        if 'LIMIT' in query_upper:
            summary_parts.append("with result limit")
        
        summary = " ".join(summary_parts) if summary_parts else "Performs a database query"
        
        # Add complexity note
        complexity = analysis.get('query_complexity', 'unknown')
        summary += f". Complexity: {complexity}."
        
        # Add issue count
        issues_count = len(analysis.get('issues', []))
        if issues_count > 0:
            summary += f" {issues_count} potential issue(s) detected."
        
        return summary
    
    def _estimate_improvement(self, analysis: Dict, optimizations: List[str]) -> str:
        """Estimate performance improvement percentage"""
        improvement_score = 0
        
        # Score based on issues resolved
        issues = analysis.get('issues', [])
        for issue in issues:
            severity = issue.get('severity', 'low')
            if severity == 'critical':
                improvement_score += 40
            elif severity == 'high':
                improvement_score += 25
            elif severity == 'medium':
                improvement_score += 15
            else:
                improvement_score += 5
        
        # Score based on optimizations applied
        improvement_score += len(optimizations) * 10
        
        # Cap at reasonable estimate
        improvement_score = min(improvement_score, 80)
        
        if improvement_score >= 50:
            return "Estimated 40-60% improvement"
        elif improvement_score >= 30:
            return "Estimated 20-40% improvement"
        elif improvement_score >= 15:
            return "Estimated 10-20% improvement"
        else:
            return "Minor optimization (< 10% improvement)"
    
    def _generate_actionable_suggestions(
        self, 
        analysis: Dict, 
        plan_interpretation: Dict, 
        index_suggestions: List[Dict]
    ) -> List[str]:
        """Generate prioritized, actionable suggestions"""
        suggestions = []
        
        # Critical issues first
        critical_issues = [
            issue for issue in analysis.get('issues', []) 
            if issue.get('severity') == 'critical'
        ]
        for issue in critical_issues:
            suggestions.append(f"🔴 CRITICAL: {issue.get('suggestion', '')}")
        
        # Query plan inefficiencies
        for inefficiency in plan_interpretation.get('inefficiencies', []):
            suggestions.append(f"⚠️  {inefficiency}")
        
        # Index recommendations
        if index_suggestions:
            suggestions.append(
                f"📊 Consider adding {len(index_suggestions)} index(es) for better performance"
            )
        
        # General performance tips
        for tip in analysis.get('performance_tips', [])[:3]:  # Top 3 tips
            suggestions.append(f"💡 {tip}")
        
        return suggestions if suggestions else ["Query appears well-optimized"]

    # -------------------------------------------------------------------------
    # Deep LLM-powered diagnosis (for your 1–6 feature list)
    # -------------------------------------------------------------------------
    def deep_diagnose_query(
        self,
        sql: str,
        schema_text: Optional[str] = None,
        execution_plan: Optional[List[Dict[str, Any]]] = None,
        profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        LLM-powered deep diagnosis of a SQL query.

        Produces:
        1) performance_diagnosis
        2) step_by_step_optimizations (with index / join / sargability / scans / aggregation)
        3) alternative_queries
        4) schema_improvements
        5) cost_category
        6) security_and_reliability
        """
        if not self.llm:
            return {
                "success": False,
                "message": "LLM not initialized for deep diagnosis",
            }

        # Fallback schema text if not provided
        if not schema_text:
            try:
                if db_connection and hasattr(db_connection, "generate_schema_text"):
                    schema_text = db_connection.generate_schema_text()
                else:
                    schema_text = "No schema text available."
            except Exception as e:
                self.logger.warning(f"Could not get schema text for deep diagnosis: {e}")
                schema_text = "No schema text available."

        plan_str = json.dumps(execution_plan or [], indent=2)
        profile_str = json.dumps(profile or {}, indent=2)

        prompt = PromptTemplate(
            input_variables=["sql", "schema_text", "execution_plan", "profile"],
            template="""
You are an expert SQL performance engineer and database architect.

You will receive:
- A SQL query
- Database schema description
- (Optional) execution plan
- (Optional) profiling metrics

Your job is to produce a JSON object that gives a DEEP diagnostic report with the following fields:

1. "performance_diagnosis": A concise but detailed explanation of inefficiencies in the query.
   - Mention problematic patterns (full scans, bad joins, non-sargable predicates, misuse of functions, etc.).
   - Refer to execution_plan/profile if present.

2. "step_by_step_optimizations": An ordered list of concrete steps to improve the query, each item like:
   - "description": short explanation
   - "category": one of ["index", "join", "filter_sargability", "scan_reduction", "aggregation", "other"]
   - "details": more implementation details
   - "example": a small SQL fragment or explanation
   Include:
     - Index recommendations (with column order, and indicate if B-Tree or composite index)
     - Better JOIN patterns or subquery usage
     - Sargability and filter improvements
     - Rewrite patterns to reduce full table scans
     - Aggregation optimization (GROUP BY / HAVING)

3. "alternative_queries": A list of 1-3 alternative SQL queries that produce the SAME RESULT but are more efficient.
   - They MUST be valid SQL for the given schema_text (do not invent tables/columns).
   - Each item should be an object:
       { "label": "e.g. 'Using EXISTS instead of IN'", "sql": "SELECT ..." }

4. "schema_improvements": Suggestions at the schema/data level such as:
   - Partitioning strategies
   - New or composite indexes
   - Normalization or denormalization
   - Materialized views
   - Column type changes or constraints
   Each item: { "suggestion": "...", "reason": "...", "impact": "low|medium|high" }

5. "cost_category": One of ["low", "medium", "high"], representing approximate query cost/complexity.
   - Base this on joins, aggregations, expected data volume, and available indexes (from schema_text and profile).

6. "security_and_reliability": Discuss risks like:
   - SQL injection potential (if this SQL string looks like it might be concatenated in app code)
   - Locking and blocking risks
   - Race conditions or non-repeatable reads
   - Use of unsafe patterns (e.g. SELECT * in critical paths, or missing WHERE in UPDATE/DELETE)
   Provide as a list of objects with:
   - "risk": short title
   - "description": details
   - "severity": "low|medium|high"
   - "mitigation": how to fix or avoid it

IMPORTANT RULES:
- Use ONLY tables and columns that are compatible with the schema_text. Do NOT invent new table or column names.
- If execution_plan or profile are empty, say that you're inferring based on typical behavior.
- Return ONLY a single valid JSON object, no markdown, no extra commentary.

Here is the input:

[SQL QUERY]
{sql}

[SCHEMA]
{schema_text}

[EXECUTION PLAN]
{execution_plan}

[PROFILE METRICS]
{profile}

Now respond with the JSON object:
"""
        )

        chain = LLMChain(llm=self.llm, prompt=prompt)

        try:
            raw = chain.run(
                sql=sql,
                schema_text=schema_text,
                execution_plan=plan_str,
                profile=profile_str,
            )
            raw = raw.strip()
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

            data = json.loads(raw)
            return {
                "success": True,
                "report": data,
            }
        except Exception as e:
            self.logger.warning(f"Deep diagnosis failed or could not parse JSON: {e}")
            return {
                "success": False,
                "message": f"Deep diagnosis failed: {e}",
            }

    # -------------------------------------------------------------------------
    # High-level: build a unified deep_analysis object for frontend
    # -------------------------------------------------------------------------
    def build_deep_analysis(
        self,
        sql: str,
        mode: str = "sql",
        natural_query: Optional[str] = None,
        original_query: Optional[str] = None,
        schema_text: Optional[str] = None,
        execution_plan: Optional[List[Dict[str, Any]]] = None,
        profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build a unified deep analysis object combining:
        - rule-based analysis
        - query plan interpretation
        - LLM deep diagnosis (1–6 features)
        
        This is what llm_routes should attach as `deep_analysis` for BOTH:
        - natural language → generated SQL
        - raw SQL → optimized SQL
        """
        # 1) Rule-based analysis of the final SQL
        basic_analysis = self.analyze_query(sql) or {}
        if not basic_analysis.get("success", True):
            basic_analysis = {
                "issues": [],
                "suggestions": [],
                "performance_tips": [],
                "query_complexity": "unknown",
            }

        # 2) Interpret query plan (if provided)
        plan_interpretation = self.interpret_query_plan(execution_plan or [])

        # 3) LLM deep diagnosis (best-effort)
        deep_report_result = self.deep_diagnose_query(
            sql=sql,
            schema_text=schema_text,
            execution_plan=execution_plan,
            profile=profile,
        )
        deep_report = deep_report_result.get("report") if deep_report_result.get("success") else None

        # Extract deep fields with safe fallbacks
        performance_diagnosis = (
            deep_report.get("performance_diagnosis")
            if isinstance(deep_report, dict)
            else None
        )
        step_by_step_optimizations = (
            deep_report.get("step_by_step_optimizations")
            if isinstance(deep_report, dict)
            else None
        )
        alternative_queries = (
            deep_report.get("alternative_queries")
            if isinstance(deep_report, dict)
            else None
        )
        schema_improvements = (
            deep_report.get("schema_improvements")
            if isinstance(deep_report, dict)
            else None
        )
        cost_category = (
            deep_report.get("cost_category")
            if isinstance(deep_report, dict)
            else None
        )
        security_and_reliability = (
            deep_report.get("security_and_reliability")
            if isinstance(deep_report, dict)
            else None
        )

        # Fallback performance diagnosis if LLM failed
        if not performance_diagnosis:
            performance_diagnosis = (
                plan_interpretation.get("summary")
                or "No detailed performance diagnosis available."
            )

        # Fallback cost category from complexity
        if not cost_category:
            complexity = basic_analysis.get("query_complexity", "unknown")
            if complexity in ("simple", "moderate"):
                cost_category = "low" if complexity == "simple" else "medium"
            else:
                cost_category = "high"

        return {
            "mode": mode,
            "natural_query": natural_query,
            "original_query": original_query,
            "final_sql": sql,
            "summary": self._generate_query_summary(sql, basic_analysis),
            "performance_diagnosis": performance_diagnosis,
            "step_by_step_optimizations": step_by_step_optimizations or [],
            "alternative_queries": alternative_queries or [],
            "schema_improvements": schema_improvements or [],
            "cost_category": cost_category,
            "security_and_reliability": security_and_reliability or [],
            "rule_based": {
                "complexity": basic_analysis.get("query_complexity", "unknown"),
                "issues": basic_analysis.get("issues", []),
                "suggestions": basic_analysis.get("suggestions", []),
                "performance_tips": basic_analysis.get("performance_tips", []),
            },
            "plan_interpretation": plan_interpretation,
            "llm_deep_report_raw": deep_report if isinstance(deep_report, dict) else None,
        }


# Global optimizer instance
optimizer_agent = OptimizerAgent()
