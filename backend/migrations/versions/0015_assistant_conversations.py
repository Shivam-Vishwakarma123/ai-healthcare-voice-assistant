"""Add assistant conversations and messages for patient consultation history.

Revision ID: 0015_assistant_conversations
Revises: 0014_invoice_refund_status
Create Date: 2026-10-22
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_assistant_conversations"
down_revision = "0014_invoice_refund_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="Health Consultation"),
        sa.Column("urgency_level", sa.String(length=40), nullable=False, server_default="routine"),
        sa.Column("category", sa.String(length=80), nullable=False, server_default="general"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("consent_given", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assistant_conversations_conversation_id", "assistant_conversations", ["conversation_id"], unique=True)
    op.create_index("ix_assistant_conversations_user_id", "assistant_conversations", ["user_id"], unique=False)
    op.create_index("ix_assistant_conversations_patient_id", "assistant_conversations", ["patient_id"], unique=False)

    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["assistant_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assistant_messages_conversation_id", "assistant_messages", ["conversation_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_assistant_messages_conversation_id", table_name="assistant_messages")
    op.drop_table("assistant_messages")
    op.drop_index("ix_assistant_conversations_patient_id", table_name="assistant_conversations")
    op.drop_index("ix_assistant_conversations_user_id", table_name="assistant_conversations")
    op.drop_index("ix_assistant_conversations_conversation_id", table_name="assistant_conversations")
    op.drop_table("assistant_conversations")
