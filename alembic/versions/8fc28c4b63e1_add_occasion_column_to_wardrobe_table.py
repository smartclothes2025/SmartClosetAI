"""Add occasion column to wardrobe table

Revision ID: 8fc28c4b63e1
Revises: 
Create Date: 2025-06-18 16:57:25.493497

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8fc28c4b63e1'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 創建新資料表
    op.create_table(
        'wardrobe_new',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('filename', sa.String, nullable=False),
        sa.Column('category', sa.String, nullable=False),
        sa.Column('color', sa.String),
        sa.Column('style', sa.String),
        sa.Column('occasion', sa.String),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False)
    )

    # 將舊資料表中的數據遷移到新資料表
    op.execute('INSERT INTO wardrobe_new (id, filename, category, color, style, user_id) SELECT id, filename, category, color, style, user_id FROM wardrobe')

    # 刪除舊資料表
    op.drop_table('wardrobe')

    # 重命名新資料表
    op.rename_table('wardrobe_new', 'wardrobe')


def downgrade() -> None:
    """Downgrade schema."""
    # 恢復舊資料表
    op.create_table(
        'wardrobe_old',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('filename', sa.String, nullable=False),
        sa.Column('category', sa.String, nullable=False),
        sa.Column('color', sa.String),
        sa.Column('style', sa.String),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False)
    )

    # 將新資料表中的數據遷移到舊資料表
    op.execute('INSERT INTO wardrobe_old (id, filename, category, color, style, user_id) SELECT id, filename, category, color, style, user_id FROM wardrobe')

    # 刪除新資料表
    op.drop_table('wardrobe')

    # 重命名舊資料表
    op.rename_table('wardrobe_old', 'wardrobe')
