"""users + reviews tables — initial schema."""

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

import sqlalchemy as sa
from alembic import op


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column("email", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("video_path", sa.String(255), nullable=False),
        sa.Column("decision", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("analysis_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_reviews_user_id", "reviews", ["user_id"])


def downgrade():
    op.drop_index("ix_reviews_user_id", table_name="reviews")
    op.drop_table("reviews")
    op.drop_table("users")
