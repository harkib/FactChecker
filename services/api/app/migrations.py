"""Database migration runner using Alembic."""
import os
from pathlib import Path

from alembic.config import Config
from alembic import command

from shared.logger import get_logger

logger = get_logger("migrations")


async def run_migrations() -> None:
    """Run Alembic migrations to upgrade database to head revision.
    
    Creates a sync engine for Alembic (which requires synchronous operations).
    """
    logger.info("Starting database migrations")
    
    try:
        # Get the path to alembic.ini (in services/api directory)
        # From app/migrations.py, we need to go up to services/api
        api_dir = Path(__file__).parent.parent
        alembic_ini_path = api_dir / "alembic.ini"
        
        if not alembic_ini_path.exists():
            logger.error(f"Alembic config not found at {alembic_ini_path}")
            raise FileNotFoundError(f"Alembic config not found at {alembic_ini_path}")
        
        # Create Alembic config
        alembic_cfg = Config(str(alembic_ini_path))
        
        # Set the database URL in the config (sync URL for Alembic)
        db_user = os.getenv("DB_USER")
        db_password = os.getenv("DB_PASSWORD")
        db_host = os.getenv("DB_HOST")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME")
        
        sync_url = f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
        
        # Run upgrade to head (Alembic handles engine creation internally)
        command.upgrade(alembic_cfg, "head")
        
        logger.info("Database migrations completed successfully")
        
    except Exception as e:
        logger.error("Failed to run database migrations", exc_info=True, error=str(e))
        raise
