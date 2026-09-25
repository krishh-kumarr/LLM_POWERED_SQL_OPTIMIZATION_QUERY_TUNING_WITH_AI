"""
Database Connection Model
==========================
Handles database connections for MySQL, PostgreSQL, and SQLite.
Extracts schema information including tables, columns, and relationships.
"""

from sqlalchemy import create_engine, inspect, MetaData, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import logging
import json

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Manages database connections and schema extraction"""
    
    def __init__(self):
        self.engine = None
        self.connection = None
        self.metadata = None
        self.db_type = None
        self.schema_info = {}
        
    def connect(self, db_config):
        """
        Establish database connection
        
        Args:
            db_config (dict): Database configuration
                - db_type: 'mysql', 'postgresql', or 'sqlite'
                - host: Database host
                - port: Database port
                - database: Database name
                - username: Database user (not needed for SQLite)
                - password: Database password (not needed for SQLite)
                - db_path: Path to SQLite file (only for SQLite)
        
        Returns:
            dict: Connection status and message
        """
        try:
            self.db_type = db_config.get('db_type', 'sqlite').lower()
            
            # Build connection string based on database type
            if self.db_type == 'sqlite':
                db_path = db_config.get('db_path', 'sample_db.sqlite')
                connection_string = f"sqlite:///{db_path}"
                
            elif self.db_type == 'mysql':
                host = db_config.get('host', 'localhost')
                port = db_config.get('port', 3306)
                database = db_config.get('database')
                username = db_config.get('username')
                password = db_config.get('password', '')
                
                connection_string = f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
                
            elif self.db_type == 'postgresql':
                host = db_config.get('host', 'localhost')
                port = db_config.get('port', 5432)
                database = db_config.get('database')
                username = db_config.get('username')
                password = db_config.get('password', '')
                
                connection_string = f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}"
                
            else:
                return {
                    'success': False,
                    'message': f"Unsupported database type: {self.db_type}"
                }
            
            # Create engine and test connection
            self.engine = create_engine(connection_string, echo=False)
            self.connection = self.engine.connect()
            
            # Test the connection
            self.connection.execute(text("SELECT 1"))
            
            logger.info(f"Successfully connected to {self.db_type} database")
            
            return {
                'success': True,
                'message': f"Successfully connected to {self.db_type} database",
                'db_type': self.db_type
            }
            
        except SQLAlchemyError as e:
            logger.error(f"Database connection error: {str(e)}")
            return {
                'success': False,
                'message': f"Connection failed: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Unexpected error during connection: {str(e)}")
            return {
                'success': False,
                'message': f"Unexpected error: {str(e)}"
            }
    
    def extract_schema(self):
        """
        Extract complete database schema including tables, columns, and relationships
        
        Returns:
            dict: Schema information with tables, columns, types, and relationships
        """
        if not self.engine:
            return {
                'success': False,
                'message': 'No active database connection'
            }
        
        try:
            inspector = inspect(self.engine)
            schema_data = {
                'tables': [],
                'relationships': []
            }
            
            # Get all table names
            table_names = inspector.get_table_names()
            
            for table_name in table_names:
                table_info = {
                    'name': table_name,
                    'columns': [],
                    'primary_keys': [],
                    'foreign_keys': []
                }
                
                # Get column information
                columns = inspector.get_columns(table_name)
                for column in columns:
                    column_info = {
                        'name': column['name'],
                        'type': str(column['type']),
                        'nullable': column['nullable'],
                        'default': str(column['default']) if column['default'] else None
                    }
                    table_info['columns'].append(column_info)
                
                # Get primary keys
                pk_constraint = inspector.get_pk_constraint(table_name)
                if pk_constraint:
                    table_info['primary_keys'] = pk_constraint.get('constrained_columns', [])
                
                # Get foreign keys
                foreign_keys = inspector.get_foreign_keys(table_name)
                for fk in foreign_keys:
                    fk_info = {
                        'constrained_columns': fk['constrained_columns'],
                        'referred_table': fk['referred_table'],
                        'referred_columns': fk['referred_columns']
                    }
                    table_info['foreign_keys'].append(fk_info)
                    
                    # Add to relationships
                    schema_data['relationships'].append({
                        'from_table': table_name,
                        'from_columns': fk['constrained_columns'],
                        'to_table': fk['referred_table'],
                        'to_columns': fk['referred_columns']
                    })
                
                schema_data['tables'].append(table_info)
            
            # Store schema info for later use
            self.schema_info = schema_data
            
            logger.info(f"Successfully extracted schema with {len(table_names)} tables")
            
            return {
                'success': True,
                'schema': schema_data,
                'table_count': len(table_names)
            }
            
        except Exception as e:
            logger.error(f"Error extracting schema: {str(e)}")
            return {
                'success': False,
                'message': f"Schema extraction failed: {str(e)}"
            }
    
    def generate_schema_text(self):
        """
        Generate human-readable schema description for RAG pipeline
        
        Returns:
            str: Formatted schema description
        """
        if not self.schema_info:
            return "No schema information available"
        
        schema_text = "Database Schema:\n\n"
        
        for table in self.schema_info.get('tables', []):
            schema_text += f"Table: {table['name']}\n"
            schema_text += "Columns:\n"
            
            for column in table['columns']:
                nullable = "NULL" if column['nullable'] else "NOT NULL"
                pk_marker = " (PRIMARY KEY)" if column['name'] in table['primary_keys'] else ""
                schema_text += f"  - {column['name']}: {column['type']} {nullable}{pk_marker}\n"
            
            if table['foreign_keys']:
                schema_text += "Foreign Keys:\n"
                for fk in table['foreign_keys']:
                    schema_text += f"  - {', '.join(fk['constrained_columns'])} -> {fk['referred_table']}({', '.join(fk['referred_columns'])})\n"
            
            schema_text += "\n"
        
        return schema_text
    
    def generate_data_dictionary_text(self, include_sample_data=True, sample_size=5):
        """
        Generate comprehensive data dictionary as formatted text with sample data
        
        Args:
            include_sample_data (bool): Whether to include sample values
            sample_size (int): Number of sample rows to fetch per table
        
        Returns:
            str: Detailed data dictionary in text format
        """
        if not self.schema_info:
            return "No schema information available"
        
        dictionary = "=" * 80 + "\n"
        dictionary += "DATABASE DATA DICTIONARY\n"
        dictionary += "=" * 80 + "\n\n"
        
        dictionary += f"Database Type: {self.db_type.upper()}\n"
        dictionary += f"Total Tables: {len(self.schema_info.get('tables', []))}\n"
        dictionary += f"Total Relationships: {len(self.schema_info.get('relationships', []))}\n\n"
        
        # Tables section
        for table in self.schema_info.get('tables', []):
            dictionary += "=" * 80 + "\n"
            dictionary += f"TABLE: {table['name']}\n"
            dictionary += "=" * 80 + "\n\n"
            
            # Column details
            dictionary += "COLUMNS:\n"
            dictionary += "-" * 80 + "\n"
            for column in table['columns']:
                nullable = "NULL" if column['nullable'] else "NOT NULL"
                pk_marker = " [PRIMARY KEY]" if column['name'] in table.get('primary_keys', []) else ""
                default = f" DEFAULT: {column['default']}" if column['default'] else ""
                
                dictionary += f"  • {column['name']}\n"
                dictionary += f"    Type: {column['type']}\n"
                dictionary += f"    Constraints: {nullable}{pk_marker}{default}\n"
                
                # Add sample data if requested
                if include_sample_data and self.connection:
                    try:
                        sample_query = f"SELECT DISTINCT {column['name']} FROM {table['name']} WHERE {column['name']} IS NOT NULL LIMIT {sample_size}"
                        result = self.connection.execute(text(sample_query))
                        samples = [str(row[0]) for row in result.fetchall()]
                        if samples:
                            dictionary += f"    Sample Values: {', '.join(samples)}\n"
                    except Exception as e:
                        logger.debug(f"Could not fetch samples for {table['name']}.{column['name']}: {str(e)}")
                
                dictionary += "\n"
            
            # Primary Keys
            if table.get('primary_keys'):
                dictionary += "\nPRIMARY KEY:\n"
                dictionary += "-" * 80 + "\n"
                dictionary += f"  {', '.join(table['primary_keys'])}\n\n"
            
            # Foreign Keys
            if table.get('foreign_keys'):
                dictionary += "FOREIGN KEYS (RELATIONSHIPS):\n"
                dictionary += "-" * 80 + "\n"
                for fk in table['foreign_keys']:
                    dictionary += f"  • {', '.join(fk['constrained_columns'])} "
                    dictionary += f"→ {fk['referred_table']}({', '.join(fk['referred_columns'])})\n"
                dictionary += "\n"
            
            # Get row count
            if self.connection:
                try:
                    count_query = f"SELECT COUNT(*) FROM {table['name']}"
                    result = self.connection.execute(text(count_query))
                    row_count = result.scalar()
                    dictionary += f"ESTIMATED ROW COUNT: {row_count:,}\n"
                except Exception as e:
                    logger.debug(f"Could not get row count for {table['name']}: {str(e)}")
            
            dictionary += "\n\n"
        
        # Relationships summary
        if self.schema_info.get('relationships'):
            dictionary += "=" * 80 + "\n"
            dictionary += "DATABASE RELATIONSHIPS SUMMARY\n"
            dictionary += "=" * 80 + "\n\n"
            
            for rel in self.schema_info['relationships']:
                dictionary += f"  {rel['from_table']}({', '.join(rel['from_columns'])}) "
                dictionary += f"→ {rel['to_table']}({', '.join(rel['to_columns'])})\n"
            
            dictionary += "\n"
        
        dictionary += "=" * 80 + "\n"
        dictionary += "END OF DATA DICTIONARY\n"
        dictionary += "=" * 80 + "\n"
        
        return dictionary
    
    def save_data_dictionary(self, filename='data_dictionary.txt', include_sample_data=True):
        """
        Save data dictionary to a text file
        
        Args:
            filename (str): Output filename
            include_sample_data (bool): Whether to include sample values
        
        Returns:
            dict: Save status
        """
        try:
            dictionary = self.generate_data_dictionary_text(include_sample_data=include_sample_data)
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(dictionary)
            
            logger.info(f"Data dictionary saved to {filename}")
            
            return {
                'success': True,
                'filename': filename,
                'message': f'Data dictionary saved successfully to {filename}'
            }
        except Exception as e:
            logger.error(f"Error saving data dictionary: {str(e)}")
            return {
                'success': False,
                'message': f'Failed to save data dictionary: {str(e)}'
            }
    
    
    def generate_data_dictionary(self):
        """
        Generate comprehensive data dictionary with sample data for better LLM context
        
        Returns:
            dict: Complete data dictionary with schema, samples, and relationships
        """
        if not self.engine or not self.schema_info:
            return {
                'success': False,
                'message': 'No active database connection or schema'
            }
        
        try:
            data_dictionary = {
                'database_type': self.db_type,
                'tables': [],
                'relationships': self.schema_info.get('relationships', [])
            }
            
            for table in self.schema_info.get('tables', []):
                table_dict = {
                    'name': table['name'],
                    'description': f"Table containing {table['name']} records",
                    'columns': [],
                    'primary_keys': table['primary_keys'],
                    'foreign_keys': table['foreign_keys'],
                    'row_count': 0,
                    'sample_data': []
                }
                
                # Get row count
                try:
                    count_query = f"SELECT COUNT(*) as count FROM {table['name']}"
                    result = self.connection.execute(text(count_query))
                    table_dict['row_count'] = result.fetchone()[0]
                except:
                    table_dict['row_count'] = 0
                
                # Enhanced column information with sample values + semantic hints
                for column in table['columns']:
                    column_dict = {
                        'name': column['name'],
                        'type': str(column['type']),
                        'nullable': column['nullable'],
                        'is_primary_key': column['name'] in table['primary_keys'],
                        'is_foreign_key': any(column['name'] in fk['constrained_columns'] for fk in table['foreign_keys']),
                        'sample_values': [],
                        'unique_count': 0,
                        'semantic_hint': ""  # NEW: meaning / usage hint for LLM
                    }
                    
                    # --- SCHEMA-SPECIFIC SEMANTIC HINTS (E-COMMERCE-LIKE SCHEMA) ---
                    # Products table – naming & price usage
                    if table['name'] == "products":
                        if column['name'] == "product_name":
                            column_dict['semantic_hint'] = (
                                "Human-readable product name. "
                                "Use this when selecting or grouping by product; "
                                "there is no generic 'name' column."
                            )
                        elif column['name'] == "price":
                            column_dict['semantic_hint'] = (
                                "Current list price of the product. "
                                "Do NOT use this column for historical revenue if order_items.unit_price exists. "
                                "For revenue or sales calculations, prefer order_items.quantity * order_items.unit_price "
                                "or orders.total_amount."
                            )

                    # Categories table – category_name
                    if table['name'] == "categories":
                        if column['name'] == "category_name":
                            column_dict['semantic_hint'] = (
                                "Name of the product category. "
                                "Use this when grouping metrics such as revenue or sales by category."
                            )

                    # Order items – quantity & unit_price
                    if table['name'] == "order_items":
                        if column['name'] == "quantity":
                            column_dict['semantic_hint'] = (
                                "Number of units for this product in a single order line. "
                                "Use this for units_sold and in revenue calculations together with unit_price."
                            )
                        elif column['name'] == "unit_price":
                            column_dict['semantic_hint'] = (
                                "Price per unit actually charged for this order line at order time. "
                                "ALWAYS use quantity * unit_price for revenue or sales amount calculations, "
                                "instead of products.price."
                            )

                    # Orders – total_amount
                    if table['name'] == "orders":
                        if column['name'] == "total_amount":
                            column_dict['semantic_hint'] = (
                                "Total monetary value of the entire order. "
                                "Use this for order-level revenue or metrics like average order value."
                            )
                    
                    # Get sample distinct values (up to 5)
                    try:
                        sample_query = f"SELECT DISTINCT {column['name']} FROM {table['name']} WHERE {column['name']} IS NOT NULL LIMIT 5"
                        result = self.connection.execute(text(sample_query))
                        column_dict['sample_values'] = [str(row[0]) for row in result.fetchall()]
                    except:
                        column_dict['sample_values'] = []
                    
                    # Get unique value count for cardinality info
                    try:
                        unique_query = f"SELECT COUNT(DISTINCT {column['name']}) as unique_count FROM {table['name']}"
                        result = self.connection.execute(text(unique_query))
                        column_dict['unique_count'] = result.fetchone()[0]
                    except:
                        column_dict['unique_count'] = 0
                    
                    table_dict['columns'].append(column_dict)
                
                # Get sample rows (up to 3) for context
                try:
                    column_names = [col['name'] for col in table['columns']]
                    sample_query = f"SELECT * FROM {table['name']} LIMIT 3"
                    result = self.connection.execute(text(sample_query))
                    rows = result.fetchall()
                    
                    for row in rows:
                        sample_row = {}
                        for idx, col_name in enumerate(column_names):
                            sample_row[col_name] = str(row[idx]) if row[idx] is not None else None
                        table_dict['sample_data'].append(sample_row)
                except:
                    table_dict['sample_data'] = []
                
                data_dictionary['tables'].append(table_dict)
            
            logger.info(f"Generated comprehensive data dictionary for {len(data_dictionary['tables'])} tables")
            
            return {
                'success': True,
                'data_dictionary': data_dictionary
            }
            
        except Exception as e:
            logger.error(f"Error generating data dictionary: {str(e)}")
            return {
                'success': False,
                'message': f'Failed to generate data dictionary: {str(e)}'
            }
    
    def format_data_dictionary_for_llm(self, data_dict):
        """
        Format data dictionary into comprehensive text for LLM context
        
        Args:
            data_dict (dict): Data dictionary from generate_data_dictionary()
        
        Returns:
            str: Formatted text optimized for LLM understanding
        """
        if not data_dict or not data_dict.get('tables'):
            return "No data dictionary available"
        
        formatted_text = f"=== DATABASE INFORMATION ===\n"
        formatted_text += f"Database Type: {data_dict.get('database_type', 'unknown')}\n"
        formatted_text += f"Total Tables: {len(data_dict['tables'])}\n\n"
        
        formatted_text += "=== DETAILED TABLE SCHEMAS ===\n\n"
        
        for table in data_dict['tables']:
            formatted_text += f"TABLE: {table['name']}\n"
            formatted_text += f"Description: {table['description']}\n"
            formatted_text += f"Row Count: {table['row_count']:,}\n"
            formatted_text += f"Primary Keys: {', '.join(table['primary_keys']) if table['primary_keys'] else 'None'}\n\n"
            
            formatted_text += "COLUMNS:\n"
            for col in table['columns']:
                formatted_text += f"  • {col['name']}\n"
                formatted_text += f"    - Type: {col['type']}\n"
                formatted_text += f"    - Nullable: {'Yes' if col['nullable'] else 'No'}\n"
                formatted_text += f"    - Primary Key: {'Yes' if col['is_primary_key'] else 'No'}\n"
                formatted_text += f"    - Foreign Key: {'Yes' if col['is_foreign_key'] else 'No'}\n"
                formatted_text += f"    - Unique Values: {col['unique_count']:,}\n"
                if col['sample_values']:
                    formatted_text += f"    - Sample Values: {', '.join(col['sample_values'][:3])}\n"
                if col.get('semantic_hint'):
                    formatted_text += f"    - Meaning: {col['semantic_hint']}\n"
                formatted_text += "\n"
            
            if table['foreign_keys']:
                formatted_text += "FOREIGN KEY RELATIONSHIPS:\n"
                for fk in table['foreign_keys']:
                    formatted_text += f"  • {', '.join(fk['constrained_columns'])} references "
                    formatted_text += f"{fk['referred_table']}({', '.join(fk['referred_columns'])})\n"
                formatted_text += "\n"
            
            if table['sample_data']:
                formatted_text += "SAMPLE DATA (first 3 rows):\n"
                for idx, row in enumerate(table['sample_data'], 1):
                    formatted_text += f"  Row {idx}: {row}\n"
                formatted_text += "\n"
            
            formatted_text += "-" * 80 + "\n\n"
        
        # Add relationship summary
        if data_dict.get('relationships'):
            formatted_text += "=== TABLE RELATIONSHIPS ===\n\n"
            for rel in data_dict['relationships']:
                formatted_text += f"• {rel['from_table']}.{','.join(rel['from_columns'])} → "
                formatted_text += f"{rel['to_table']}.{','.join(rel['to_columns'])}\n"
            formatted_text += "\n"
        
        formatted_text += "=== QUERY GENERATION GUIDELINES ===\n"
        formatted_text += "1. Use ONLY the table and column names listed above\n"
        formatted_text += "2. Respect foreign key relationships for JOIN operations\n"
        formatted_text += "3. Consider data types when using WHERE conditions\n"
        formatted_text += "4. Use primary keys for efficient lookups\n"
        formatted_text += "5. Check sample values to understand data patterns\n"
        
        return formatted_text
    
    def execute_query(self, query):
        """
        Execute SQL query and return results
        
        Args:
            query (str): SQL query to execute
        
        Returns:
            dict: Query results or error message
        """
        if not self.connection:
            return {
                'success': False,
                'message': 'No active database connection'
            }
        
        try:
            result = self.connection.execute(text(query))
            
            # Check if query returns results
            if result.returns_rows:
                rows = result.fetchall()
                columns = list(result.keys())
                
                # Convert to list of dictionaries
                data = []
                for row in rows:
                    data.append(dict(zip(columns, row)))
                
                return {
                    'success': True,
                    'data': data,
                    'columns': columns,
                    'row_count': len(data)
                }
            else:
                return {
                    'success': True,
                    'message': 'Query executed successfully',
                    'rows_affected': result.rowcount
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Query execution error: {str(e)}")
            return {
                'success': False,
                'message': f"Query execution failed: {str(e)}"
            }
    
    def get_query_plan(self, query):
        """
        Get query execution plan using EXPLAIN
        
        Args:
            query (str): SQL query to analyze
        
        Returns:
            dict: Query execution plan
        """
        if not self.connection:
            return {
                'success': False,
                'message': 'No active database connection'
            }
        
        try:
            # Different databases use different EXPLAIN syntax
            if self.db_type == 'sqlite':
                explain_query = f"EXPLAIN QUERY PLAN {query}"
            elif self.db_type == 'postgresql':
                explain_query = f"EXPLAIN (FORMAT JSON) {query}"
            elif self.db_type == 'mysql':
                explain_query = f"EXPLAIN FORMAT=JSON {query}"
            else:
                explain_query = f"EXPLAIN {query}"
            
            result = self.connection.execute(text(explain_query))
            plan = result.fetchall()
            
            return {
                'success': True,
                'plan': [dict(row._mapping) for row in plan]
            }
            
        except Exception as e:
            logger.error(f"Error getting query plan: {str(e)}")
            return {
                'success': False,
                'message': f"Could not retrieve query plan: {str(e)}"
            }
    
    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")
        if self.engine:
            self.engine.dispose()


# Global database connection instance
db_connection = DatabaseConnection()
