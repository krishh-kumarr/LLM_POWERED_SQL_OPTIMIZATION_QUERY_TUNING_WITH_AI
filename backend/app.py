"""
AI SQL Copilot - Main Flask Application
========================================
This is the entry point for the Flask backend server.
Handles CORS, blueprint registration, and error handling.
"""

from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_app():
    """Application factory pattern for Flask app creation"""
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
    app.config['JSON_SORT_KEYS'] = False
    
    # CORS setup - Allow frontend to communicate with backend
    # In development, allow all origins to avoid CORS issues
    is_dev = os.getenv('FLASK_ENV', 'development') == 'development' or os.getenv('FLASK_DEBUG', 'True') == 'True'
    if is_dev:
        # Allow all origins in development (for easier local development)
        CORS(app, resources={
            r"/api/*": {
                "origins": "*",  # Allow all origins in development
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "allow_headers": ["Content-Type", "Authorization"],
                "supports_credentials": False
            }
        })
        logger.info("CORS configured for development (allowing all origins)")
    else:
        # Production: use specific origins from environment
        cors_origins = os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(',')
        CORS(app, resources={
            r"/api/*": {
                "origins": cors_origins,
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "allow_headers": ["Content-Type", "Authorization"]
            }
        })
        logger.info(f"CORS configured for production with origins: {cors_origins}")
    
    # Register blueprints
    from routes.db_routes import db_bp
    from routes.llm_routes import llm_bp
    from routes.query_routes import query_bp
    
    app.register_blueprint(db_bp, url_prefix='/api')
    app.register_blueprint(llm_bp, url_prefix='/api')
    app.register_blueprint(query_bp, url_prefix='/api')
    
    # Health check endpoint
    @app.route('/api/health', methods=['GET'])
    def health_check():
        """Health check endpoint to verify server is running"""
        return jsonify({
            'status': 'healthy',
            'message': 'AI SQL Copilot API is running'
        }), 200
    
    # Global error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Endpoint not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {str(error)}")
        return jsonify({'error': 'Internal server error'}), 500
    
    @app.errorhandler(Exception)
    def handle_exception(error):
        logger.error(f"Unhandled exception: {str(error)}")
        return jsonify({'error': str(error)}), 500
    
    logger.info("Flask application initialized successfully")
    return app

# Create app instance
app = create_app()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    debug = os.getenv('FLASK_DEBUG', 'True') == 'True'
    
    logger.info(f"Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
