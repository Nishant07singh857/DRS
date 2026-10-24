"""Add calibration_profiles table (spec G: camera calibration)

Revision ID: 0003_calibration
Revises: 0002_umpire
"""

revision = '0003_calibration'
down_revision = '0002_umpire'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'calibration_profiles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('camera_id', sa.Integer(),
                  sa.ForeignKey('cameras.id'), unique=True, nullable=False),
        sa.Column('data', sa.JSON()),
        sa.Column('reprojection_error', sa.Float()),
        sa.Column('is_calibrated', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )
    op.create_index('ix_calibration_camera', 'calibration_profiles', ['camera_id'])


def downgrade():
    op.drop_index('ix_calibration_camera', 'calibration_profiles')
    op.drop_table('calibration_profiles')
