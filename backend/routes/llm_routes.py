"""
LLM Routes
==========
API endpoints for LLM-powered SQL generation and optimization.
"""

from flask import Blueprint, request, jsonify
from services.rag_pipeline import rag_service
from services.optimizer_agent import optimizer_agent
from services.sql_profiler import sql_profiler
from models.db_connection import db_connection
import logging

logger = logging.getLogger(__name__)

# Create blueprint
llm_bp = Blueprint('llm', __name__)


def _get_db_type(default: str = "sqlite") -> str:
    """Safely get database type from db_connection."""
    try:
        if db_connection and getattr(db_connection, "db_type", None):
            return db_connection.db_type
    except Exception as e:
        logger.warning(f"Could not determine db_type from db_connection: {e}")
    return default


def _get_schema_text() -> str:
    """
    Safely get schema text from db_connection.
    If unavailable, return empty string and let RAG retrieve schema via vector store.
    """
    try:
        if db_connection and hasattr(db_connection, "generate_schema_text"):
            return db_connection.generate_schema_text()
    except Exception as e:
        logger.warning(f"Could not generate schema text: {e}")
    return ""


@llm_bp.route('/generate-sql', methods=['POST'])
def generate_sql():
    """
    Generate SQL query from natural language using RAG pipeline
    
    Request Body:
    {
        "query": "Show me all customers who bought products in the last month",
        "context": "optional additional context"
    }
    
    Returns:
        JSON response with generated SQL and optimization suggestions
    """
    try:
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({
                'success': False,
                'message': 'Natural language query is required'
            }), 400
        
        natural_query = data.get('query', '').strip()
        
        if not natural_query:
            return jsonify({
                'success': False,
                'message': 'Query cannot be empty'
            }), 400
        
        # Optional override from request body, else from db_connection
        db_type = data.get('database_type') or _get_db_type(default='sqlite')
        
        # Generate optimized SQL with metadata using RAG
        # (RAG now strictly adheres to schema + auto-repairs invalid columns where possible)
        result = rag_service.generate_optimized_sql(natural_query, db_type)
        
        # If RAG layer itself failed, propagate error
        if not result.get('success', False):
            validation_errors = result.get('validation_errors') or []
            status_code = 400 if validation_errors else 500

            return jsonify({
                'success': False,
                'natural_query': natural_query,
                'generated_sql': result.get('optimized_query') or result.get('generated_sql', ''),
                'validation_errors': validation_errors,
                'message': result.get('message', 'Failed to generate SQL query')
            }), status_code
        
        # Extract SQL query (handle both 'generated_sql' and 'optimized_query' keys for compatibility)
        generated_sql = result.get('optimized_query') or result.get('generated_sql', '')
        
        if not generated_sql:
            return jsonify({
                'success': False,
                'message': 'Failed to generate SQL query'
            }), 500

        # If RAG reports validation errors (even though success=True), do NOT profile
        validation_errors = result.get('validation_errors') or []
        if validation_errors:
            logger.warning(
                "Generated SQL did not pass schema validation: %s",
                validation_errors
            )
            return jsonify({
                'success': False,
                'natural_query': natural_query,
                'generated_sql': generated_sql,
                'validation_errors': validation_errors,
                'message': 'Generated SQL did not pass schema validation. Please adjust the query or use the suggested columns/tables.'
            }), 400
        
        # Get LLM-provided optimization details
        llm_optimizations = result.get('optimizations_applied', [])
        llm_explanation = result.get('explanation', '')
        llm_suggested_indexes = result.get('suggested_indexes', [])
        
        # Also run rule-based analysis as additional validation
        analysis = optimizer_agent.analyze_query(generated_sql)
        
        # Combine LLM suggestions with rule-based index suggestions
        rule_based_indexes = optimizer_agent.suggest_indexes(generated_sql)
        # LLM returns strings, rule-based returns dicts - convert all to strings for consistency
        llm_index_strings = [str(idx) if isinstance(idx, str) else idx for idx in llm_suggested_indexes]
        rule_based_strings = [
            f"Index on {idx.get('table', '')}.{idx.get('column', '')}" if isinstance(idx, dict) else str(idx)
            for idx in rule_based_indexes
        ]
        # Combine and remove duplicates (using set of strings)
        all_index_suggestions = list(set(llm_index_strings + rule_based_strings))
        
        # Profile the generated query to get performance metrics
        performance_metrics = None
        try:
            profile_result = sql_profiler.profile_query(generated_sql)
            if profile_result.get('success'):
                # Build a rich performance object so the frontend can show DB execution time,
                # client time, memory, CPU, and query plan.
                performance_metrics = {
                    # timing
                    'db_execution_time_ms': profile_result.get('db_execution_time_ms'),
                    'db_timing_source': profile_result.get('db_timing_source'),
                    'timing_source': profile_result.get('timing_source'),
                    'fetch_time_ms': profile_result.get('fetch_time_ms'),
                    'conversion_time_ms': profile_result.get('conversion_time_ms'),
                    'total_time_ms': profile_result.get('total_time_ms'),
                    'network_time_ms': profile_result.get('network_time_ms'),
                    'network_time_is_heuristic': profile_result.get('network_time_is_heuristic'),
                    
                    # memory
                    'memory_used_mb': profile_result.get('memory_used_mb', 0),
                    'memory_calculation_method': profile_result.get('memory_calculation_method'),
                    'memory_timing_source': profile_result.get('memory_timing_source'),
                    
                    # CPU
                    'cpu_percent': profile_result.get('cpu_percent', 0),
                    'cpu_per_core_percent': profile_result.get('cpu_per_core_percent'),
                    'cpu_raw_percent': profile_result.get('cpu_raw_percent'),
                    'cpu_seconds_used': profile_result.get('cpu_seconds_used'),
                    'cpu_timing_source': profile_result.get('cpu_timing_source'),
                    
                    # result + plan
                    'row_count': profile_result.get('row_count', 0),
                    'columns': profile_result.get('columns', []),
                    'data': profile_result.get('data', [])[:10],  # First 10 rows for preview
                    'data_truncated': profile_result.get('data_truncated'),
                    'query_plan': profile_result.get('query_plan', []),
                    
                    # alias for older code
                    'execution_time_ms': profile_result.get('execution_time_ms', 0),
                }
                logger.info(
                    "Query profiled: db=%.2fms total=%.2fms rows=%d",
                    (performance_metrics['db_execution_time_ms'] or 0.0)
                    if performance_metrics['db_execution_time_ms'] is not None else 0.0,
                    performance_metrics['total_time_ms'] or 0.0,
                    performance_metrics['row_count'],
                )
            else:
                logger.warning(f"Query profiling failed: {profile_result.get('message', 'Unknown error')}")
        except Exception as e:
            logger.warning(f"Error profiling query: {str(e)}")
            # Don't fail the request if profiling fails
        
        response_data = {
            'success': True,
            'natural_query': natural_query,
            'generated_sql': generated_sql,
            'analysis': {
                'issues': analysis.get('issues', []),
                'complexity': analysis.get('query_complexity', 'unknown'),
                'suggestions': analysis.get('suggestions', []),
                'performance_tips': analysis.get('performance_tips', []),
                # Add LLM-provided optimization details
                'llm_optimizations': llm_optimizations,
                'llm_explanation': llm_explanation
            },
            'suggested_indexes': all_index_suggestions,
            'performance': performance_metrics
        }
        
        logger.info(f"Generated SQL for query: {natural_query[:50]}...")
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error in generate_sql: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500


@llm_bp.route('/optimize-query', methods=['POST'])
def optimize_query():
    """
    Optimize an existing SQL query using database context
    
    Request Body:
    {
        "query": "SELECT * FROM users WHERE age > 25"
    }
    
    Returns:
        JSON response with optimized query, analysis, and performance metrics
    """
    try:
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({
                'success': False,
                'message': 'SQL query is required'
            }), 400
        
        original_query = data.get('query', '').strip()
        
        if not original_query:
            return jsonify({
                'success': False,
                'message': 'Query cannot be empty'
            }), 400
        
        # Get schema context (if available). If empty, RAG will still use
        # vector store + STRICT allowed schema summary internally.
        schema_context = _get_schema_text()
        
        # Optimize query using RAG service (uses data dictionary / schema context)
        result = rag_service.optimize_query(original_query, schema_context)
        
        if not result.get('success', False):
            validation_errors = result.get('validation_errors') or []
            status_code = 400 if validation_errors else 500

            return jsonify({
                'success': False,
                'original_query': original_query,
                'optimized_query': result.get('optimized_query', original_query),
                'validation_errors': validation_errors,
                'message': result.get('message', 'Failed to optimize SQL query')
            }), status_code
        
        optimized_sql = result.get('optimized_query', original_query)
        optimizations_applied = result.get('optimizations_applied', [])
        explanation = result.get('explanation', '')
        
        # If there are validation errors, return them without profiling
        validation_errors = result.get('validation_errors') or []
        if validation_errors:
            logger.warning(
                "Optimized SQL did not pass schema validation: %s",
                validation_errors
            )
            return jsonify({
                'success': False,
                'original_query': original_query,
                'optimized_query': optimized_sql,
                'validation_errors': validation_errors,
                'message': 'Optimized SQL did not pass schema validation. Please adjust the query or use valid columns/tables.'
            }), 400
        
        # Check if query is already optimized (if optimized_sql is same as original)
        is_already_optimized = optimized_sql.strip().upper() == original_query.strip().upper()
        
        if is_already_optimized:
            logger.info("Query appears to be already optimized")
            explanation = "Your query appears to be already well-optimized. No changes were made."
        
        # Analyze the optimized query for issues and suggestions
        analysis = optimizer_agent.analyze_query(optimized_sql)
        
        # Get index suggestions based on the optimized query
        rule_based_indexes = optimizer_agent.suggest_indexes(optimized_sql)
        # Convert dict format to strings for consistency
        index_suggestions = [
            f"Index on {idx.get('table', '')}.{idx.get('column', '')}" if isinstance(idx, dict) else str(idx)
            for idx in rule_based_indexes
        ]
        
        # Profile both original and optimized queries for comparison
        performance_metrics = None
        original_performance = None
        
        try:
            # Profile original query first
            if not is_already_optimized:
                logger.info("Profiling original query for comparison...")
                original_profile = sql_profiler.profile_query(original_query)
                if original_profile.get('success'):
                    original_performance = {
                        # timing
                        'db_execution_time_ms': original_profile.get('db_execution_time_ms'),
                        'db_timing_source': original_profile.get('db_timing_source'),
                        'timing_source': original_profile.get('timing_source'),
                        'total_time_ms': original_profile.get('total_time_ms'),
                        'execution_time_ms': original_profile.get('execution_time_ms', 0),
                        
                        # memory & cpu
                        'memory_used_mb': original_profile.get('memory_used_mb', 0),
                        'memory_calculation_method': original_profile.get('memory_calculation_method'),
                        'cpu_percent': original_profile.get('cpu_percent', 0),
                        'cpu_per_core_percent': original_profile.get('cpu_per_core_percent'),
                        'cpu_raw_percent': original_profile.get('cpu_raw_percent'),
                        'cpu_seconds_used': original_profile.get('cpu_seconds_used'),
                        
                        # result + plan
                        'row_count': original_profile.get('row_count', 0),
                        'query_plan': original_profile.get('query_plan', []),
                    }
                    logger.info(
                        "Original query profiled: db=%.2fms total=%.2fms",
                        (original_performance['db_execution_time_ms'] or 0.0)
                        if original_performance['db_execution_time_ms'] is not None else 0.0,
                        original_performance['total_time_ms'] or 0.0,
                    )
            
            # Profile optimized query
            logger.info("Profiling optimized query...")
            profile_result = sql_profiler.profile_query(optimized_sql)
            if profile_result.get('success'):
                performance_metrics = {
                    # timing
                    'db_execution_time_ms': profile_result.get('db_execution_time_ms'),
                    'db_timing_source': profile_result.get('db_timing_source'),
                    'timing_source': profile_result.get('timing_source'),
                    'fetch_time_ms': profile_result.get('fetch_time_ms'),
                    'conversion_time_ms': profile_result.get('conversion_time_ms'),
                    'total_time_ms': profile_result.get('total_time_ms'),
                    'network_time_ms': profile_result.get('network_time_ms'),
                    'network_time_is_heuristic': profile_result.get('network_time_is_heuristic'),
                    
                    # memory
                    'memory_used_mb': profile_result.get('memory_used_mb', 0),
                    'memory_calculation_method': profile_result.get('memory_calculation_method'),
                    
                    # CPU
                    'cpu_percent': profile_result.get('cpu_percent', 0),
                    'cpu_per_core_percent': profile_result.get('cpu_per_core_percent'),
                    'cpu_raw_percent': profile_result.get('cpu_raw_percent'),
                    'cpu_seconds_used': profile_result.get('cpu_seconds_used'),
                    'cpu_timing_source': profile_result.get('cpu_timing_source'),
                    
                    # result + plan
                    'row_count': profile_result.get('row_count', 0),
                    'query_plan': profile_result.get('query_plan', []),
                    'data': profile_result.get('data', [])[:10],  # First 10 rows for preview
                    'columns': profile_result.get('columns', []),
                    'data_truncated': profile_result.get('data_truncated'),
                    
                    # alias
                    'execution_time_ms': profile_result.get('execution_time_ms', 0),
                }
                
                # Add comparison metrics if we have original performance
                if original_performance:
                    orig_time = original_performance['execution_time_ms']
                    opt_time = performance_metrics['execution_time_ms']
                    time_improvement = orig_time - opt_time
                    time_improvement_percent = (time_improvement / orig_time * 100) if orig_time > 0 else 0.0
                    
                    memory_improvement = original_performance['memory_used_mb'] - performance_metrics['memory_used_mb']
                    memory_improvement_percent = (
                        (memory_improvement / original_performance['memory_used_mb'] * 100)
                        if original_performance['memory_used_mb'] > 0 else 0.0
                    )
                    
                    performance_metrics['comparison'] = {
                        'original': original_performance,
                        'optimized': {
                            'db_execution_time_ms': performance_metrics.get('db_execution_time_ms'),
                            'db_timing_source': performance_metrics.get('db_timing_source'),
                            'total_time_ms': performance_metrics.get('total_time_ms'),
                            'execution_time_ms': performance_metrics.get('execution_time_ms', 0),
                            'memory_used_mb': performance_metrics.get('memory_used_mb', 0),
                            'cpu_percent': performance_metrics.get('cpu_percent', 0),
                            'row_count': performance_metrics.get('row_count', 0),
                            'query_plan': performance_metrics.get('query_plan', []),
                        },
                        'time_improvement_ms': round(time_improvement, 2),
                        'time_improvement_percent': round(time_improvement_percent, 2),
                        'memory_improvement_mb': round(memory_improvement, 4),
                        'memory_improvement_percent': round(memory_improvement_percent, 2),
                        'is_faster': time_improvement > 0,
                        'uses_less_memory': memory_improvement > 0
                    }
                
                logger.info(
                    "Optimized query profiled: db=%.2fms total=%.2fms rows=%d",
                    (performance_metrics['db_execution_time_ms'] or 0.0)
                    if performance_metrics['db_execution_time_ms'] is not None else 0.0,
                    performance_metrics['total_time_ms'] or 0.0,
                    performance_metrics['row_count'],
                )
            else:
                logger.warning(f"Query profiling failed: {profile_result.get('message', 'Unknown error')}")
        except Exception as e:
            logger.warning(f"Error profiling query: {str(e)}")
            # Don't fail the request if profiling fails
        
        response_data = {
            'success': True,
            'original_query': original_query,
            'optimized_query': optimized_sql,
            'is_already_optimized': is_already_optimized,
            'optimizations_applied': optimizations_applied,
            'explanation': explanation,
            'analysis': {
                'issues': analysis.get('issues', []),
                'complexity': analysis.get('query_complexity', 'unknown'),
                'suggestions': analysis.get('suggestions', []),
                'performance_tips': analysis.get('performance_tips', [])
            },
            'suggested_indexes': index_suggestions,
            'performance': performance_metrics
        }
        
        logger.info(f"Optimized query with {len(optimizations_applied)} optimizations")
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error in optimize_query: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500


@llm_bp.route('/analyze-query', methods=['POST'])
def analyze_query():
    """
    Analyze SQL query for potential issues
    
    Request Body:
    {
        "query": "SELECT * FROM users WHERE age > 25"
    }
    
    Returns:
        JSON response with analysis results
    """
    try:
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({
                'success': False,
                'message': 'SQL query is required'
            }), 400
        
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({
                'success': False,
                'message': 'Query cannot be empty'
            }), 400
        
        # Analyze query
        result = optimizer_agent.analyze_query(query)
        
        # Get index suggestions
        result['suggested_indexes'] = optimizer_agent.suggest_indexes(query)
        
        logger.info(f"Analyzed query: {result.get('issues_count', 0)} issues found")
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error in analyze_query: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500


@llm_bp.route('/get-suggestions', methods=['POST'])
def get_suggestions():
    """
    Get optimization suggestions for a SQL query
    
    Request Body:
    {
        "query": "SELECT * FROM users where age > 25"
    }
    
    Returns:
        JSON response with suggestions and recommendations
    """
    try:
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({
                'success': False,
                'message': 'SQL query is required'
            }), 400
        
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({
                'success': False,
                'message': 'Query cannot be empty'
            }), 400
        
        # Analyze query
        analysis = optimizer_agent.analyze_query(query)
        
        # Get index suggestions
        index_suggestions = optimizer_agent.suggest_indexes(query)
        
        response = {
            'success': True,
            'query': query,
            'suggestions': analysis.get('suggestions', []),
            'issues': analysis.get('issues', []),
            'performance_tips': analysis.get('performance_tips', []),
            'suggested_indexes': index_suggestions,
            'complexity': analysis.get('query_complexity', 'unknown')
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Error in get_suggestions: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500


@llm_bp.route('/generate-example-queries', methods=['GET'])
def generate_example_queries_endpoint():
    """
    Generate example natural language queries based on the current database schema
    
    Query Parameters:
        count (int, optional): Number of example queries to generate (default: 5)
    
    Returns:
        JSON response with list of example queries relevant to the database
    """
    try:
        # Check database connection safely
        if not db_connection or not getattr(db_connection, "connection", None):
            return jsonify({
                'success': False,
                'message': 'No active database connection. Please connect first.'
            }), 400
        
        # Get count parameter (default: 5)
        count = request.args.get('count', 5, type=int)
        count = max(1, min(count, 10))  # Limit between 1 and 10
        
        # Generate example queries based on schema
        result = rag_service.generate_example_queries(count=count)
        
        if not result.get('success'):
            return jsonify(result), 400
        
        return jsonify({
            'success': True,
            'example_queries': result.get('example_queries', []),
            'count': len(result.get('example_queries', []))
        }), 200
        
    except Exception as e:
        logger.error(f"Error in generate_example_queries: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500
