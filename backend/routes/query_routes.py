"""
Query Routes
============
API endpoints for query execution and performance profiling.
"""

from flask import Blueprint, request, jsonify
from services.sql_profiler import sql_profiler
from services.optimizer_agent import optimizer_agent
from models.db_connection import db_connection
import logging

logger = logging.getLogger(__name__)

# Create blueprint
query_bp = Blueprint('query', __name__)


@query_bp.route('/run-query', methods=['POST'])
def run_query():
    """
    Execute SQL query and return results with profiling metrics
    
    Request Body:
    {
        "query": "SELECT * FROM users LIMIT 10"
    }
    
    Returns:
        JSON response with query results and performance metrics
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
        
        # Check database connection
        if not db_connection.connection:
            return jsonify({
                'success': False,
                'message': 'No active database connection. Please connect first.'
            }), 400
        
        # Profile and execute query
        result = sql_profiler.profile_query(query)
        
        if not result['success']:
            return jsonify(result), 400
        
        logger.info(f"Query executed: {result['row_count']} rows, {result['execution_time_ms']}ms")
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error in run_query: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500


@query_bp.route('/compare-queries', methods=['POST'])
def compare_queries():
    """
    Compare performance of original and optimized queries
    
    Request Body:
    {
        "original_query": "SELECT * FROM users WHERE age > 25",
        "optimized_query": "SELECT id, name, age FROM users WHERE age > 25"
    }
    
    Returns:
        JSON response with performance comparison
    """
    try:
        data = request.get_json()
        
        if not data or 'original_query' not in data or 'optimized_query' not in data:
            return jsonify({
                'success': False,
                'message': 'Both original_query and optimized_query are required'
            }), 400
        
        original_query = data.get('original_query', '').strip()
        optimized_query = data.get('optimized_query', '').strip()
        
        if not original_query or not optimized_query:
            return jsonify({
                'success': False,
                'message': 'Queries cannot be empty'
            }), 400
        
        # Check database connection
        if not db_connection.connection:
            return jsonify({
                'success': False,
                'message': 'No active database connection. Please connect first.'
            }), 400
        
        # Compare queries
        result = sql_profiler.compare_queries(original_query, optimized_query)
        
        if not result['success']:
            return jsonify(result), 400
        
        logger.info(f"Query comparison: {result['improvements']['time_improvement_percent']}% improvement")
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error in compare_queries: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500


@query_bp.route('/profile-query', methods=['POST'])
def profile_query():
    """
    Profile a SQL query without returning full results
    
    Request Body:
    {
        "query": "SELECT * FROM users WHERE age > 25"
    }
    
    Returns:
        JSON response with profiling metrics only
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
        
        # Check database connection
        if not db_connection.connection:
            return jsonify({
                'success': False,
                'message': 'No active database connection. Please connect first.'
            }), 400
        
        # Profile query
        result = sql_profiler.profile_query(query)
        
        if not result['success']:
            return jsonify(result), 400
        
        # Remove data to only return metrics
        profiling_metrics = {
            'success': True,
            'query': result['query'],
            'execution_time_ms': result['execution_time_ms'],
            'memory_used_mb': result['memory_used_mb'],
            'cpu_percent': result['cpu_percent'],
            'row_count': result['row_count'],
            'query_plan': result['query_plan']
        }
        
        logger.info(f"Query profiled: {result['execution_time_ms']}ms")
        
        return jsonify(profiling_metrics), 200
        
    except Exception as e:
        logger.error(f"Error in profile_query: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500


@query_bp.route('/system-metrics', methods=['GET'])
def get_system_metrics():
    """
    Get current system performance metrics
    
    Returns:
        JSON response with CPU, memory, and disk usage
    """
    try:
        result = sql_profiler.get_system_metrics()
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error in get_system_metrics: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500


@query_bp.route('/comprehensive-optimization', methods=['POST'])
def comprehensive_optimization():
    """
    Perform comprehensive query optimization with full analysis
    Generates a non-optimal query first, then provides optimized version for comparison
    
    Request Body:
    {
        "query": "SELECT * FROM users WHERE age > 25" (non-optimal query)
    }
    OR
    {
        "nl_query": "Show me all users older than 25" (natural language - will generate both versions)
    }
    
    Returns:
        JSON response with structured optimization analysis
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'Request body is required'
            }), 400
        
        # Check database connection
        if not db_connection.connection:
            return jsonify({
                'success': False,
                'message': 'No active database connection. Please connect first.'
            }), 400
        
        # Get schema context
        schema_result = db_connection.get_schema()
        schema_context = ""
        if schema_result['success']:
            data_dict = db_connection.generate_data_dictionary()
            if data_dict['success']:
                schema_context = db_connection.format_data_dictionary_for_llm(data_dict['data_dictionary'])
        
        query = None
        
        # Handle natural language query
        if 'nl_query' in data:
            nl_query = data.get('nl_query', '').strip()
            if not nl_query:
                return jsonify({
                    'success': False,
                    'message': 'Natural language query cannot be empty'
                }), 400
            
            logger.info(f"Generating SQL from natural language: {nl_query}")
            
            # Import here to avoid circular dependency
            from services.rag_pipeline import rag_service
            
            # Generate initial SQL (non-optimal version)
            generation_result = rag_service.generate_sql(nl_query, schema_context)
            
            if not generation_result['success']:
                return jsonify({
                    'success': False,
                    'message': f"Failed to generate SQL: {generation_result.get('message', 'Unknown error')}"
                }), 400
            
            # Fix: generate_sql() returns 'generated_sql' not 'sql_query'
            query = generation_result.get('generated_sql', '')
            if not query:
                return jsonify({
                    'success': False,
                    'message': 'Failed to generate SQL query'
                }), 400
            
            logger.info(f"Generated initial query: {query}")
        
        # Handle direct SQL query
        elif 'query' in data:
            query = data.get('query', '').strip()
            if not query:
                return jsonify({
                    'success': False,
                    'message': 'Query cannot be empty'
                }), 400
        else:
            return jsonify({
                'success': False,
                'message': 'Either "query" or "nl_query" is required'
            }), 400
        
        # Profile the original (non-optimal) query
        logger.info("Profiling original query...")
        original_profile = sql_profiler.profile_query(query)
        
        if not original_profile['success']:
            return jsonify({
                'success': False,
                'message': f"Failed to execute original query: {original_profile.get('message', 'Unknown error')}",
                'query': query
            }), 400
        
        original_time = original_profile.get('execution_time_ms', 0)
        logger.info(f"Original query executed in {original_time}ms")
        
        # Perform comprehensive optimization
        logger.info("Performing comprehensive optimization...")
        optimization_result = optimizer_agent.comprehensive_optimization(
            original_query=query,
            schema_context=schema_context,
            execution_time_original=original_time
        )
        
        if not optimization_result['success']:
            return jsonify(optimization_result), 400
        
        # Profile the optimized query
        optimized_query = optimization_result['optimized_query']
        logger.info("Profiling optimized query...")
        
        optimized_profile = sql_profiler.profile_query(optimized_query)
        
        if optimized_profile['success']:
            optimized_time = optimized_profile.get('execution_time_ms', 0)
            logger.info(f"Optimized query executed in {optimized_time}ms")
            
            # Calculate actual improvement
            if original_time > 0:
                improvement_percent = ((original_time - optimized_time) / original_time) * 100
                optimization_result['performance_comparison'] = {
                    'original_time_ms': original_time,
                    'optimized_time_ms': optimized_time,
                    'improvement_ms': original_time - optimized_time,
                    'improvement_percent': round(improvement_percent, 2),
                    'improvement_summary': f"{abs(round(improvement_percent, 1))}% {'faster' if improvement_percent > 0 else 'slower'}"
                }
            
            # Include results in response
            optimization_result['original_results'] = {
                'row_count': original_profile.get('row_count', 0),
                'data': original_profile.get('data', [])[:5]  # First 5 rows
            }
            optimization_result['optimized_results'] = {
                'row_count': optimized_profile.get('row_count', 0),
                'data': optimized_profile.get('data', [])[:5]  # First 5 rows
            }
        else:
            logger.warning(f"Optimized query execution failed: {optimized_profile.get('message')}")
            optimization_result['performance_comparison']['note'] = 'Optimized query validation failed'
        
        logger.info("Comprehensive optimization completed successfully")
        return jsonify(optimization_result), 200
        
    except Exception as e:
        logger.error(f"Error in comprehensive_optimization: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500
