"""Allow invoice status to reflect partial and completed refunds."""

from alembic import op
import sqlalchemy as sa

revision = "0014_invoice_refund_status"
down_revision = "0013_payment_refunds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("invoices", "status", existing_type=sa.String(length=16), type_=sa.String(length=24), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("invoices", "status", existing_type=sa.String(length=24), type_=sa.String(length=16), existing_nullable=False)
