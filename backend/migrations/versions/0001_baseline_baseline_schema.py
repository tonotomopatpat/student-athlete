"""baseline schema

Revision ID: 0001_baseline
Revises: 
Create Date: 2026-11-27 13:39:29.442870
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = '0001_baseline'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('q_cells',
    sa.Column('state', sa.String(length=30), nullable=False),
    sa.Column('action', sa.String(length=30), nullable=False),
    sa.Column('q_value', sa.Double(), nullable=False),
    sa.Column('visits', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('state', 'action')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('sport', sa.String(length=80), nullable=True),
    sa.Column('study_window_start', sa.Integer(), nullable=False),
    sa.Column('study_window_end', sa.Integer(), nullable=False),
    sa.Column('buffer_minutes', sa.Integer(), nullable=False),
    sa.Column('reminder_minutes', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)

    op.create_table('commitments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=160), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('start_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.Column('end_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.Column('repeat_weekly', sa.Boolean(), nullable=False),
    sa.Column('repeat_until', sa.Date(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('commitments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_commitments_user_id'), ['user_id'], unique=False)

    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('event_key', sa.String(length=120), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('title', sa.String(length=160), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('link', sa.String(length=120), nullable=True),
    sa.Column('scheduled_for', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.Column('pushed_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('read_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('created_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'event_key')
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notifications_user_id'), ['user_id'], unique=False)

    op.create_table('push_subscriptions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('endpoint', sa.String(length=600), nullable=False),
    sa.Column('p256dh', sa.String(length=255), nullable=False),
    sa.Column('auth', sa.String(length=255), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('endpoint')
    )
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_push_subscriptions_user_id'), ['user_id'], unique=False)

    op.create_table('subjects',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=30), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.Column('is_sample', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    with op.batch_alter_table('subjects', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_subjects_owner_id'), ['owner_id'], unique=False)

    op.create_table('enrollments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('subject_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'subject_id')
    )
    with op.batch_alter_table('enrollments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_enrollments_user_id'), ['user_id'], unique=False)

    op.create_table('topics',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('subject_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('p_l0', sa.Double(), nullable=False),
    sa.Column('p_t', sa.Double(), nullable=False),
    sa.Column('p_g', sa.Double(), nullable=False),
    sa.Column('p_s', sa.Double(), nullable=False),
    sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('subject_id', 'name')
    )
    with op.batch_alter_table('topics', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_topics_subject_id'), ['subject_id'], unique=False)

    op.create_table('materials',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('subject_id', sa.Integer(), nullable=False),
    sa.Column('topic_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('stored_name', sa.String(length=80), nullable=True),
    sa.Column('original_name', sa.String(length=255), nullable=True),
    sa.Column('mime_type', sa.String(length=100), nullable=True),
    sa.Column('uploader_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['uploader_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('materials', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_materials_subject_id'), ['subject_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_materials_topic_id'), ['topic_id'], unique=False)

    op.create_table('questions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('topic_id', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('choices', sa.JSON(), nullable=False),
    sa.Column('correct_index', sa.Integer(), nullable=False),
    sa.Column('explanation', sa.Text(), nullable=False),
    sa.Column('is_diagnostic', sa.Boolean(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_questions_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_questions_topic_id'), ['topic_id'], unique=False)

    op.create_table('recommendations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('topic_id', sa.Integer(), nullable=False),
    sa.Column('activity_type', sa.String(length=30), nullable=False),
    sa.Column('state_key', sa.String(length=30), nullable=False),
    sa.Column('q_value', sa.Double(), nullable=False),
    sa.Column('explored', sa.Boolean(), nullable=False),
    sa.Column('epsilon', sa.Double(), nullable=False),
    sa.Column('available_minutes', sa.Double(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('mastery_before', sa.Double(), nullable=True),
    sa.Column('mastery_after', sa.Double(), nullable=True),
    sa.Column('reward', sa.Double(), nullable=True),
    sa.Column('next_state_key', sa.String(length=30), nullable=True),
    sa.Column('q_value_after', sa.Double(), nullable=True),
    sa.Column('created_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.Column('completed_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('recommendations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recommendations_user_id'), ['user_id'], unique=False)

    op.create_table('requirements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('subject_id', sa.Integer(), nullable=True),
    sa.Column('topic_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(length=160), nullable=False),
    sa.Column('due_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.Column('done', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('requirements', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_requirements_user_id'), ['user_id'], unique=False)

    op.create_table('topic_mastery',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('topic_id', sa.Integer(), nullable=False),
    sa.Column('p_mastery', sa.Double(), nullable=False),
    sa.Column('response_count', sa.Integer(), nullable=False),
    sa.Column('diagnostic_done', sa.Boolean(), nullable=False),
    sa.Column('last_activity_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'topic_id')
    )
    with op.batch_alter_table('topic_mastery', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_topic_mastery_user_id'), ['user_id'], unique=False)

    op.create_table('responses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('question_id', sa.Integer(), nullable=False),
    sa.Column('topic_id', sa.Integer(), nullable=False),
    sa.Column('recommendation_id', sa.Integer(), nullable=True),
    sa.Column('context', sa.String(length=20), nullable=False),
    sa.Column('chosen_index', sa.Integer(), nullable=False),
    sa.Column('correct', sa.Boolean(), nullable=False),
    sa.Column('mastery_before', sa.Double(), nullable=False),
    sa.Column('mastery_after', sa.Double(), nullable=False),
    sa.Column('created_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recommendation_id'], ['recommendations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('responses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_responses_topic_id'), ['topic_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_responses_user_id'), ['user_id'], unique=False)

    op.create_table('study_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('recommendation_id', sa.Integer(), nullable=False),
    sa.Column('start_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('end_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.ForeignKeyConstraint(['recommendation_id'], ['recommendations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('recommendation_id')
    )
    with op.batch_alter_table('study_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_study_sessions_user_id'), ['user_id'], unique=False)



def downgrade() -> None:
    # Dropping a table drops its indexes; MySQL refuses to drop an index a foreign key still needs.
    op.drop_table('study_sessions')
    op.drop_table('responses')
    op.drop_table('topic_mastery')
    op.drop_table('requirements')
    op.drop_table('recommendations')
    op.drop_table('questions')
    op.drop_table('materials')
    op.drop_table('topics')
    op.drop_table('enrollments')
    op.drop_table('subjects')
    op.drop_table('push_subscriptions')
    op.drop_table('notifications')
    op.drop_table('commitments')
    op.drop_table('users')
    op.drop_table('q_cells')
