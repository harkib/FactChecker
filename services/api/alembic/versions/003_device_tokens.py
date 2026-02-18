"""Add device_tokens table for push notification registration

Revision ID: 003_device_tokens
Revises: 002_add_failed
Create Date: 2024-01-03 00:00:00.000000

"""
import os
import sys
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Add parent directory to path to import shared modules and migration helpers
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from migration_helpers import table_exists

# revision identifiers, used by Alembic.
revision: str = '003_device_tokens'
down_revision: Union[str, None] = '002_add_failed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create device_tokens table if it doesn't exist."""
    if table_exists('device_tokens'):
        return

    op.create_table(
        'device_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('client_id', sa.String(length=255), nullable=False),
        sa.Column('device_token', sa.Text(), nullable=False),
        sa.Column('sns_endpoint_arn', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    )
    op.create_index('ix_device_tokens_client_id', 'device_tokens', ['client_id'], unique=False)


def downgrade() -> None:
    """Drop device_tokens table."""
    if table_exists('device_tokens'):
        op.drop_index('ix_device_tokens_client_id', table_name='device_tokens')
        op.drop_table('device_tokens')
