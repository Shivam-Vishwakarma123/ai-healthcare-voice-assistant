"""Persist provider refund requests and outcomes."""

from alembic import op
import sqlalchemy as sa

revision = "0013_payment_refunds"
down_revision = "0012_rbac_test_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("payments", "status", existing_type=sa.String(length=16), type_=sa.String(length=24), existing_nullable=False)
    op.create_table(
        "payment_refunds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("provider_refund_id", sa.String(80), nullable=True, unique=True),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_payment_refunds_payment_id", "payment_refunds", ["payment_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_refunds_payment_id", table_name="payment_refunds")
    op.drop_table("payment_refunds")
    op.alter_column("payments", "status", existing_type=sa.String(length=24), type_=sa.String(length=16), existing_nullable=False)
