"""Initial schema

Revision ID: 001_initial
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
import os
import sys
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Add parent directory to path to import shared modules and migration helpers
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import Job
from migration_helpers import table_exists, column_exists, index_exists

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create jobs table using ORM definition if it doesn't exist."""
    # Check if table already exists
    if table_exists('jobs'):
        return
    
    # Create jobs table using ORM column definitions from Job model
    # Reference: Job model in services/shared/database.py
    op.create_table(
        'jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('video_url', sa.Text(), nullable=False),  # Job.video_url
        sa.Column('status', sa.String(length=50), nullable=False),  # Job.status
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),  # Job.created_at
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=True),  # Job.updated_at
        sa.Column('video_s3_key', sa.Text(), nullable=True),  # Job.video_s3_key
        sa.Column('transcript_s3_key', sa.Text(), nullable=True),  # Job.transcript_s3_key
        sa.Column('frames_s3_prefix', sa.Text(), nullable=True),  # Job.frames_s3_prefix
        sa.Column('claims', postgresql.JSONB(astext_type=sa.Text()), nullable=True),  # Job.claims
        sa.Column('verified_claims', postgresql.JSONB(astext_type=sa.Text()), nullable=True),  # Job.verified_claims
        sa.Column('error_message', sa.Text(), nullable=True),  # Job.error_message
        sa.Column('client_id', sa.String(length=255), nullable=False),  # Job.client_id
        sa.Column('title', sa.Text(), nullable=True),  # Job.title
    )
    
    # Create index if it doesn't exist (Job.client_id has index=True)
    if not index_exists('jobs', 'ix_jobs_client_id'):
        op.create_index('ix_jobs_client_id', 'jobs', ['client_id'], unique=False)


def downgrade() -> None:
    """Drop jobs table and its index."""
    if index_exists('jobs', 'ix_jobs_client_id'):
        op.drop_index('ix_jobs_client_id', table_name='jobs')
    
    if table_exists('jobs'):
        op.drop_table('jobs')
