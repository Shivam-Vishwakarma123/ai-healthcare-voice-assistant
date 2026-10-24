"""Add patient vitals observation table.

Revision ID: 0017_patient_vitals
Revises: 0016_clinical_records
Create Date: 2026-10-24
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_patient_vitals"
down_revision = "0016_clinical_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patient_vitals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_user_id", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bp_systolic", sa.Integer(), nullable=True),
        sa.Column("bp_diastolic", sa.Integer(), nullable=True),
        sa.Column("heart_rate", sa.Integer(), nullable=True),
        sa.Column("spo2", sa.Integer(), nullable=True),
        sa.Column("temperature_f", sa.Float(), nullable=True),
        sa.Column("respiratory_rate", sa.Integer(), nullable=True),
        sa.Column("blood_glucose", sa.Float(), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="normal"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="clinical_encounter"),
        sa.Column("encounter_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["patient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["encounter_id"], ["appointments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_patient_vitals_patient_user_id", "patient_vitals", ["patient_user_id"], unique=False)
    op.create_index("ix_patient_vitals_encounter_id", "patient_vitals", ["encounter_id"], unique=False)
    op.create_index("ix_patient_vitals_recorded_at", "patient_vitals", ["recorded_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_patient_vitals_recorded_at", table_name="patient_vitals")
    op.drop_index("ix_patient_vitals_encounter_id", table_name="patient_vitals")
    op.drop_index("ix_patient_vitals_patient_user_id", table_name="patient_vitals")
    op.drop_table("patient_vitals")
