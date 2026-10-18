"""Add umpire control center fields to reviews

Revision ID: 0002_umpire
Revises: 0001_initial
"""

revision = '0002_umpire'
down_revision = '0001_initial'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('reviews', sa.Column('review_type', sa.String(20),
                                       server_default='LBW'))
    op.add_column('reviews', sa.Column('status', sa.String(20),
                                       server_default='pending'))
    op.add_column('reviews', sa.Column('match_id', sa.Integer()))
    op.add_column('reviews', sa.Column('delivery_id', sa.Integer()))
    op.add_column('reviews', sa.Column('original_call', sa.String(20)))
    op.add_column('reviews', sa.Column('ai_recommendation', sa.String(20)))
    op.add_column('reviews', sa.Column('ai_confidence', sa.Float()))
    op.add_column('reviews', sa.Column('final_decision', sa.String(20)))
    op.add_column('reviews', sa.Column('confirmed_by', sa.Integer()))
    op.add_column('reviews', sa.Column('confirmed_at', sa.DateTime()))
    op.add_column('reviews', sa.Column('confirmation_note', sa.String(500)))
    op.add_column('reviews', sa.Column('is_locked', sa.Boolean(),
                                       server_default='false'))
    op.add_column('reviews', sa.Column('evidence', sa.JSON()))
    op.add_column('reviews', sa.Column('updated_at', sa.DateTime()))
    op.create_index('ix_reviews_status', 'reviews', ['status'])
    op.create_index('ix_reviews_match', 'reviews', ['match_id'])


def downgrade():
    op.drop_index('ix_reviews_match', 'reviews')
    op.drop_index('ix_reviews_status', 'reviews')
    for col in ['review_type', 'status', 'match_id', 'delivery_id',
                'original_call', 'ai_recommendation', 'ai_confidence',
                'final_decision', 'confirmed_by', 'confirmed_at',
                'confirmation_note', 'is_locked', 'evidence', 'updated_at']:
        op.drop_column('reviews', col)
