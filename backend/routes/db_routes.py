"""
Database Routes
===============
API endpoints for database connection and schema management.
"""

from flask import Blueprint, request, jsonify
from models.db_connection import db_connection
from services.rag_pipeline import rag_service
import logging

logger = logging.getLogger(__name__)

# Create blueprint
db_bp = Blueprint('db', __name__)


@db_bp.route('/connect-db', methods=['POST'])
def connect_database():
    """
    Connect to database and extract schema
    
    Request Body:
    {
        "db_type": "sqlite|mysql|postgresql",
        "host": "localhost",
        "port": 3306,
        "database": "db_name",
        "username": "user",
        "password": "pass",
        "db_path": "path/to/sqlite.db"  // For SQLite only
    }
    
    Returns:
        JSON response with connection status and schema information
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        # Validate required fields based on db_type
        db_type = data.get('db_type', 'sqlite').lower()
        
        if db_type not in ['sqlite', 'mysql', 'postgresql']:
            return jsonify({
                'success': False,
                'message': f'Unsupported database type: {db_type}'
            }), 400
        
        # Connect to database
        connection_result = db_connection.connect(data)
        
        if not connection_result['success']:
            return jsonify(connection_result), 400
        
        # Extract schema
        schema_result = db_connection.extract_schema()
        
        if not schema_result['success']:
            return jsonify(schema_result), 500
        
        # Generate comprehensive data dictionary
        data_dict_result = db_connection.generate_data_dictionary()
        
        if not data_dict_result['success']:
            logger.warning(f"Failed to generate data dictionary: {data_dict_result.get('message')}")
            data_dictionary_text = db_connection.generate_schema_text()
        else:
            # Format data dictionary for LLM
            data_dictionary_text = db_connection.format_data_dictionary_for_llm(
                data_dict_result['data_dictionary']
            )
        
        # Save data dictionary to file for review
        db_name = data.get('database', data.get('db_path', 'database'))
        data_dict_filename = f"data_dictionary_{db_type}_{db_name.replace('/', '_').replace('.sqlite', '')}.txt"
        save_result = db_connection.save_data_dictionary(
            filename=data_dict_filename,
            include_sample_data=True
        )
        
        if save_result['success']:
            logger.info(f"Data dictionary saved to: {data_dict_filename}")
        
        # Store comprehensive data dictionary in vector database
        try:
            rag_service.index_schema(
                data_dictionary_text, 
                schema_result['schema'],
                data_dict_result.get('data_dictionary')
            )
            logger.info("Data dictionary indexed in vector store successfully")
        except Exception as e:
            logger.warning(f"Failed to index data dictionary in vector store: {str(e)}")
            # Don't fail the request if vector indexing fails
        
        return jsonify({
            'success': True,
            'message': 'Successfully connected and extracted schema with data dictionary',
            'db_type': connection_result['db_type'],
            'schema': schema_result['schema'],
            'table_count': schema_result['table_count'],
            'data_dictionary_generated': data_dict_result['success'],
            'data_dictionary_file': data_dict_filename if save_result['success'] else None
        }), 200
        
    except Exception as e:
        logger.error(f"Error in connect_database: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500


@db_bp.route('/get-schema', methods=['GET'])
def get_schema():
    """
    Get current database schema
    
    Returns:
        JSON response with schema information
    """
    try:
        if not db_connection.schema_info:
            return jsonify({
                'success': False,
                'message': 'No active database connection. Please connect first.'
            }), 400
        
        return jsonify({
            'success': True,
            'schema': db_connection.schema_info,
            'schema_text': db_connection.generate_schema_text()
        }), 200
        
    except Exception as e:
        logger.error(f"Error in get_schema: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500


@db_bp.route('/get-data-dictionary', methods=['GET'])
def get_data_dictionary():
    """
    Get the generated data dictionary as text
    
    Returns:
        Plain text data dictionary
    """
    try:
        if not db_connection.schema_info:
            return jsonify({
                'success': False,
                'message': 'No active database connection. Please connect first.'
            }), 400
        
        data_dictionary = db_connection.generate_data_dictionary_text(include_sample_data=True)
        
        return data_dictionary, 200, {'Content-Type': 'text/plain; charset=utf-8'}
        
    except Exception as e:
        logger.error(f"Error in get_data_dictionary: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500


@db_bp.route('/disconnect-db', methods=['POST'])
def disconnect_database():
    """
    Disconnect from current database
    
    Returns:
        JSON response with disconnection status
    """
    try:
        db_connection.close()
        
        return jsonify({
            'success': True,
            'message': 'Database disconnected successfully'
        }), 200
        
    except Exception as e:
        logger.error(f"Error in disconnect_database: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500
