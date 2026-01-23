"""Add failed column to jobs table

Revision ID: 002_add_failed
Revises: 001_initial
Create Date: 2024-01-02 00:00:00.000000

"""
import os
import sys
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# Add parent directory to path to import shared modules and migration helpers
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import Job
from migration_helpers import column_exists

# revision identifiers, used by Alembic.
revision: str = '002_add_failed'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'failed' column to jobs table using ORM definition if it doesn't exist."""
    # Check if column already exists
    if column_exists('jobs', 'failed'):
        return
    
    # Add 'failed' column using ORM definition from Job model
    # Job.failed = Column(Boolean, nullable=True, default=False)
    op.add_column('jobs', Job.failed)
    # op.add_column('jobs', sa.Column('failed', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    """Remove 'failed' column from jobs table."""
    if column_exists('jobs', 'failed'):
        op.drop_column('jobs', 'failed')
