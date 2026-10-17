"""Add username login and development test-account markers."""

from alembic import op
import sqlalchemy as sa

revision = "0012_rbac_test_accounts"
down_revision = "0011_appointment_invoices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=64), nullable=True))
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.add_column(
        "users",
        sa.Column("is_test_account", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_test_account")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "username")
