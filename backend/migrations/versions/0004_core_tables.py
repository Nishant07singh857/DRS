"""Create all remaining model tables + Phase 1 security tables (BE-C2)

Revision ID: 0004_core_tables
Revises: 0003_calibration

BE-C2: before this migration, a migrated DB had only users, reviews
and calibration_profiles — no match/training/system/replay tables at
all, although all 17 models exist. This migration creates every
remaining table in dependency order, PLUS the Phase 1 security
columns/tables that Phase 1 deliberately did not ship as a migration
(Team.user_id, Match.user_id, Camera.user_id — Camera.user_id is in
0003 — Highlight.user_id, RevokedToken and TaskOwnership tables).

Dependency order (parents before children):
  organizations -> venues -> teams -> players -> matches -> innings
  -> deliveries; cameras (0003) -> bookmarks/highlights;
  users/matches/reviews -> notifications/audit_logs;
  players/venues -> training_sessions -> delivery_metrics;
  users -> revoked_tokens / task_ownership.
Cameras.venue_id / match_id FKs are added last (batch mode), once
venues and matches exist — see 0003's docstring.
"""

revision = '0004_core_tables'
down_revision = '0003_calibration'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'organizations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('org_type', sa.String(30), server_default='club'),
        sa.Column('contact_email', sa.String(120)),
        sa.Column('contact_phone', sa.String(20)),
        sa.Column('logo_url', sa.String(255)),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_table(
        'venues',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(),
                  sa.ForeignKey('organizations.id')),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('location', sa.String(200)),
        sa.Column('pitch_type', sa.String(30), server_default='turf'),
        sa.Column('calibration_profile', sa.JSON()),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_table(
        'teams',
        sa.Column('id', sa.Integer(), primary_key=True),
        # Phase 1 (SEC-C3) security column, at creation.
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('organization_id', sa.Integer(),
                  sa.ForeignKey('organizations.id')),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('short_name', sa.String(10)),
        sa.Column('logo_url', sa.String(255)),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_table(
        'players',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id'),
                  nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('jersey_number', sa.Integer()),
        sa.Column('batting_style', sa.String(20)),
        sa.Column('bowling_style', sa.String(30)),
        sa.Column('player_role', sa.String(20)),
        sa.Column('photo_url', sa.String(255)),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_table(
        'matches',
        sa.Column('id', sa.Integer(), primary_key=True),
        # Phase 1 (SEC-C3) security column, at creation.
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('organization_id', sa.Integer(),
                  sa.ForeignKey('organizations.id')),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id')),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('team_a_id', sa.Integer(), sa.ForeignKey('teams.id'),
                  nullable=False),
        sa.Column('team_b_id', sa.Integer(), sa.ForeignKey('teams.id'),
                  nullable=False),
        sa.Column('match_format', sa.String(20), server_default='T20'),
        sa.Column('overs_per_innings', sa.Integer(), server_default='20'),
        sa.Column('status', sa.String(20), server_default='scheduled'),
        sa.Column('toss_winner_id', sa.Integer(), sa.ForeignKey('teams.id')),
        sa.Column('toss_choice', sa.String(10)),
        sa.Column('config', sa.JSON()),
        sa.Column('scheduled_at', sa.DateTime()),
        sa.Column('started_at', sa.DateTime()),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_table(
        'innings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('match_id', sa.Integer(), sa.ForeignKey('matches.id'),
                  nullable=False),
        sa.Column('innings_number', sa.Integer(), nullable=False),
        sa.Column('batting_team_id', sa.Integer(), sa.ForeignKey('teams.id'),
                  nullable=False),
        sa.Column('bowling_team_id', sa.Integer(), sa.ForeignKey('teams.id'),
                  nullable=False),
        sa.Column('total_runs', sa.Integer(), server_default='0'),
        sa.Column('total_wickets', sa.Integer(), server_default='0'),
        sa.Column('total_overs', sa.Float(), server_default='0'),
        # BE-H5: total_balls = all deliveries; legal balls separately.
        sa.Column('total_balls', sa.Integer(), server_default='0'),
        sa.Column('total_legal_balls', sa.Integer(), server_default='0'),
        sa.Column('status', sa.String(20), server_default='not_started'),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_table(
        'deliveries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('innings_id', sa.Integer(), sa.ForeignKey('innings.id'),
                  nullable=False),
        sa.Column('match_id', sa.Integer(), sa.ForeignKey('matches.id'),
                  nullable=False),
        sa.Column('over_number', sa.Integer(), nullable=False),
        sa.Column('ball_number', sa.Integer(), nullable=False),
        sa.Column('ball_in_over', sa.Integer(), nullable=False),
        sa.Column('bowler_id', sa.Integer(), sa.ForeignKey('players.id')),
        sa.Column('striker_id', sa.Integer(), sa.ForeignKey('players.id')),
        sa.Column('non_striker_id', sa.Integer(),
                  sa.ForeignKey('players.id')),
        sa.Column('runs_off_bat', sa.Integer(), server_default='0'),
        sa.Column('extras', sa.JSON()),
        sa.Column('total_runs', sa.Integer(), server_default='0'),
        sa.Column('is_wicket', sa.Boolean(), server_default='false'),
        sa.Column('wicket_type', sa.String(30)),
        sa.Column('out_player_id', sa.Integer(), sa.ForeignKey('players.id')),
        sa.Column('tracking_data', sa.JSON()),
        sa.Column('review_id', sa.Integer(), sa.ForeignKey('reviews.id')),
        sa.Column('is_legal', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_table(
        'bookmarks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('match_id', sa.Integer(), sa.ForeignKey('matches.id')),
        sa.Column('delivery_id', sa.Integer(),
                  sa.ForeignKey('deliveries.id')),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('bookmark_type', sa.String(20), nullable=False),
        sa.Column('timestamp_s', sa.Float(), nullable=False),
        sa.Column('frame_number', sa.Integer()),
        sa.Column('camera_id', sa.Integer(), sa.ForeignKey('cameras.id')),
        sa.Column('note', sa.String(300)),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_table(
        'highlights',
        sa.Column('id', sa.Integer(), primary_key=True),
        # Phase 1 (SEC-C3) security column, at creation.
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('match_id', sa.Integer(), sa.ForeignKey('matches.id')),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('start_s', sa.Float(), nullable=False),
        sa.Column('end_s', sa.Float(), nullable=False),
        sa.Column('event_type', sa.String(20)),
        sa.Column('source_video', sa.String(255)),
        sa.Column('clip_path', sa.String(255)),
        sa.Column('auto_generated', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('category', sa.String(30), nullable=False),
        sa.Column('severity', sa.String(10), server_default='info'),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('message', sa.Text()),
        sa.Column('match_id', sa.Integer(), sa.ForeignKey('matches.id')),
        sa.Column('review_id', sa.Integer(), sa.ForeignKey('reviews.id')),
        sa.Column('is_read', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('entity_type', sa.String(30)),
        sa.Column('entity_id', sa.Integer()),
        sa.Column('details', sa.JSON()),
        sa.Column('ip_address', sa.String(50)),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_table(
        'training_sessions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'),
                  nullable=False),
        sa.Column('player_id', sa.Integer(), sa.ForeignKey('players.id')),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id')),
        sa.Column('session_type', sa.String(20), server_default='bowling'),
        sa.Column('title', sa.String(200)),
        sa.Column('notes', sa.Text()),
        sa.Column('target_deliveries', sa.Integer(), server_default='30'),
        sa.Column('target_area', sa.JSON()),
        sa.Column('status', sa.String(20), server_default='active'),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('completed_at', sa.DateTime()),
    )
    op.create_table(
        'delivery_metrics',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('session_id', sa.Integer(),
                  sa.ForeignKey('training_sessions.id'), nullable=False),
        sa.Column('ball_number', sa.Integer(), nullable=False),
        sa.Column('speed_kmh', sa.Float()),
        sa.Column('pitch_x', sa.Float()),
        sa.Column('pitch_y', sa.Float()),
        sa.Column('length_zone', sa.String(20)),
        sa.Column('line_zone', sa.String(30)),
        sa.Column('swing', sa.String(20)),
        sa.Column('spin', sa.String(20)),
        sa.Column('is_target_hit', sa.Boolean()),
        sa.Column('shot_angle', sa.Float()),
        sa.Column('shot_type', sa.String(30)),
        sa.Column('runs', sa.Integer(), server_default='0'),
        sa.Column('timing', sa.String(20)),
        sa.Column('created_at', sa.DateTime()),
    )
    # Phase 1 security tables (SEC-C4 / SEC-H4).
    op.create_table(
        'revoked_tokens',
        sa.Column('jti', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_table(
        'task_ownership',
        sa.Column('task_id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'),
                  nullable=False),
        sa.Column('created_at', sa.DateTime()),
    )
    # Cameras FKs, now that venues/matches exist (batch mode so this
    # also works on SQLite, which cannot ADD CONSTRAINT in place).
    with op.batch_alter_table('cameras') as batch:
        batch.create_foreign_key('fk_cameras_venue', 'venues',
                                 ['venue_id'], ['id'])
        batch.create_foreign_key('fk_cameras_match', 'matches',
                                 ['match_id'], ['id'])


def downgrade():
    with op.batch_alter_table('cameras') as batch:
        batch.drop_constraint('fk_cameras_match', type_='foreignkey')
        batch.drop_constraint('fk_cameras_venue', type_='foreignkey')
    for table in ('task_ownership', 'revoked_tokens', 'delivery_metrics',
                  'training_sessions', 'audit_logs', 'notifications',
                  'highlights', 'bookmarks', 'deliveries', 'innings',
                  'matches', 'players', 'teams', 'venues',
                  'organizations'):
        op.drop_table(table)
