"""Add cameras + calibration_profiles tables (spec E + G)

Revision ID: 0003_calibration
Revises: 0002_umpire

BE-C2 fix: the original 0003 created calibration_profiles with a FK
to cameras.id, but NO migration ever created cameras — a Postgres
`flask db upgrade` failed on the dangling FK. Cameras are therefore
created FIRST, in this same migration, before calibration_profiles.
Cameras.venue_id / match_id are plain Integer columns here (NOT FKs):
venues and matches do not exist yet at this revision, so an FK here
would be the same dangling-FK bug in reverse — 0004 creates those
tables and then adds the two FK constraints to cameras (batch mode,
so SQLite also works).
(0003 never successfully applied to a Postgres DB — it failed at this
FK — so correcting it in place breaks no deployed migrated schema;
SQLite test DBs are ephemeral.)
"""

revision = '0003_calibration'
down_revision = '0002_umpire'

from alembic import op
import sqlalchemy as sa


def upgrade():
    # Phase 1 (SEC-C3) security column included at creation: Camera.user_id.
    op.create_table(
        'cameras',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
        # Plain Integers for now — FKs added in 0004 (see docstring).
        sa.Column('venue_id', sa.Integer()),
        sa.Column('match_id', sa.Integer()),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('role', sa.String(20), server_default='main'),
        sa.Column('device_id', sa.String(100)),
        sa.Column('resolution', sa.String(20), server_default='1080p'),
        sa.Column('fps', sa.Integer(), server_default='60'),
        sa.Column('status', sa.String(20), server_default='offline'),
        sa.Column('battery_pct', sa.Integer()),
        sa.Column('storage_gb_free', sa.Float()),
        sa.Column('dropped_frames', sa.Integer(), server_default='0'),
        sa.Column('last_heartbeat', sa.DateTime()),
        sa.Column('calibration_profile_id', sa.Integer()),
        sa.Column('created_at', sa.DateTime()),
    )
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
    op.drop_table('cameras')
