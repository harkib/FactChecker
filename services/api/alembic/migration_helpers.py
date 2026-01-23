"""Helper functions for migrations to check if changes already exist."""
from alembic import op
from sqlalchemy import inspect


def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database.
    
    Args:
        table_name: Name of the table to check
        
    Returns:
        True if table exists, False otherwise
    """
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table.
    
    Args:
        table_name: Name of the table
        column_name: Name of the column to check
        
    Returns:
        True if column exists, False otherwise
    """
    bind = op.get_bind()
    inspector = inspect(bind)
    
    if not table_exists(table_name):
        return False
    
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def index_exists(table_name: str, index_name: str) -> bool:
    """Check if an index exists on a table.
    
    Args:
        table_name: Name of the table
        index_name: Name of the index to check
        
    Returns:
        True if index exists, False otherwise
    """
    bind = op.get_bind()
    inspector = inspect(bind)
    
    if not table_exists(table_name):
        return False
    
    indexes = [idx['name'] for idx in inspector.get_indexes(table_name)]
    return index_name in indexes
