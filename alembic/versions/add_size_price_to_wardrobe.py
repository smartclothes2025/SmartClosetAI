"""Add size_label and price_ntd columns to wardrobe_items table

Revision ID: add_size_price_fields
Revises: 8fc28c4b63e1
Create Date: 2025-01-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_size_price_fields'
down_revision: Union[str, None] = '9159778ca097'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add size_label and price_ntd columns."""
    op.add_column('wardrobe_items', sa.Column('size_label', sa.String(), nullable=True))
    op.add_column('wardrobe_items', sa.Column('price_ntd', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Remove size_label and price_ntd columns."""
    op.drop_column('wardrobe_items', 'price_ntd')
    op.drop_column('wardrobe_items', 'size_label')
