"""ingestion and generation jobs

Revision ID: 0002_ingestion
Revises: 0001_baseline
Create Date: 2026-11-27 13:50:19.489892
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = '0002_ingestion'
down_revision: str | Sequence[str] | None = '0001_baseline'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('generation_jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('material_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('question_count', sa.Integer(), nullable=False),
    sa.Column('error', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.Column('started_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('finished_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.ForeignKeyConstraint(['material_id'], ['materials.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('generation_jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_generation_jobs_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_generation_jobs_material_id'), ['material_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_generation_jobs_user_id'), ['user_id'], unique=False)

    op.create_table('material_sections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('material_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('level', sa.Integer(), nullable=False),
    sa.Column('page', sa.Integer(), nullable=True),
    sa.Column('word_count', sa.Integer(), nullable=False),
    sa.Column('topic_id', sa.Integer(), nullable=True),
    sa.Column('score', sa.Double(), nullable=False),
    sa.Column('assigned_by', sa.String(length=10), nullable=False),
    sa.ForeignKeyConstraint(['material_id'], ['materials.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('material_id', 'position')
    )
    with op.batch_alter_table('material_sections', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_material_sections_material_id'), ['material_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_material_sections_topic_id'), ['topic_id'], unique=False)

    with op.batch_alter_table('materials', schema=None) as batch_op:
        batch_op.add_column(sa.Column('extracted_text', sa.Text().with_variant(mysql.MEDIUMTEXT(), 'mysql'), nullable=True))
        batch_op.add_column(sa.Column('extraction_status', sa.String(length=20), server_default='pending', nullable=False))
        batch_op.add_column(sa.Column('extraction_error', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('language', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('text_hash', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_materials_text_hash'), ['text_hash'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('materials', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_materials_text_hash'))
        batch_op.drop_column('text_hash')
        batch_op.drop_column('language')
        batch_op.drop_column('extraction_error')
        batch_op.drop_column('extraction_status')
        batch_op.drop_column('extracted_text')
    op.drop_table('material_sections')
    op.drop_table('generation_jobs')
