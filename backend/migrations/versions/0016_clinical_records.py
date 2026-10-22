"""Add clinical notes, prescriptions, medical reports, allergies, and documents.

Revision ID: 0016_clinical_records
Revises: 0015_assistant_conversations
Create Date: 2026-10-22
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_clinical_records"
down_revision = "0015_assistant_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. clinical_notes
    op.create_table(
        "clinical_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_user_id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=True),
        sa.Column("note_type", sa.String(length=50), nullable=False, server_default="consultation_note"),
        sa.Column("chief_complaint", sa.Text(), nullable=True),
        sa.Column("history_of_present_illness", sa.Text(), nullable=True),
        sa.Column("examination_findings", sa.Text(), nullable=True),
        sa.Column("assessment", sa.Text(), nullable=True),
        sa.Column("plan", sa.Text(), nullable=True),
        sa.Column("follow_up_instructions", sa.Text(), nullable=True),
        sa.Column("is_ai_draft", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["patient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["finalized_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clinical_notes_patient_user_id", "clinical_notes", ["patient_user_id"], unique=False)
    op.create_index("ix_clinical_notes_doctor_id", "clinical_notes", ["doctor_id"], unique=False)
    op.create_index("ix_clinical_notes_appointment_id", "clinical_notes", ["appointment_id"], unique=False)

    # 2. prescriptions
    op.create_table(
        "prescriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prescription_number", sa.String(length=64), nullable=False),
        sa.Column("patient_user_id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=True),
        sa.Column("diagnosis", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("allergy_warnings", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("is_ai_draft", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["patient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["finalized_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prescriptions_prescription_number", "prescriptions", ["prescription_number"], unique=True)
    op.create_index("ix_prescriptions_patient_user_id", "prescriptions", ["patient_user_id"], unique=False)
    op.create_index("ix_prescriptions_doctor_id", "prescriptions", ["doctor_id"], unique=False)
    op.create_index("ix_prescriptions_appointment_id", "prescriptions", ["appointment_id"], unique=False)

    # 3. prescription_items
    op.create_table(
        "prescription_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prescription_id", sa.Integer(), nullable=False),
        sa.Column("medication_name", sa.String(length=180), nullable=False),
        sa.Column("strength", sa.String(length=60), nullable=True),
        sa.Column("dosage_form", sa.String(length=60), nullable=False, server_default="tablet"),
        sa.Column("route", sa.String(length=40), nullable=False, server_default="oral"),
        sa.Column("frequency", sa.String(length=80), nullable=False),
        sa.Column("duration", sa.String(length=80), nullable=False),
        sa.Column("quantity", sa.String(length=40), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["prescription_id"], ["prescriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prescription_items_prescription_id", "prescription_items", ["prescription_id"], unique=False)

    # 4. medical_reports
    op.create_table(
        "medical_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.String(length=64), nullable=False),
        sa.Column("patient_user_id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=True),
        sa.Column("appointment_id", sa.Integer(), nullable=True),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("report_type", sa.String(length=60), nullable=False, server_default="symptom_assessment"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("urgency_level", sa.String(length=40), nullable=False, server_default="routine"),
        sa.Column("red_flags", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("findings", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("recommended_next_steps", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("evidence_sources", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("uncertainty_notes", sa.Text(), nullable=True),
        sa.Column("disclaimer", sa.Text(), nullable=False),
        sa.Column("model_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="generated"),
        sa.Column("reviewed_by_doctor_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["patient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["conversation_id"], ["assistant_conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_doctor_id"], ["doctors.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_medical_reports_report_id", "medical_reports", ["report_id"], unique=True)
    op.create_index("ix_medical_reports_patient_user_id", "medical_reports", ["patient_user_id"], unique=False)
    op.create_index("ix_medical_reports_doctor_id", "medical_reports", ["doctor_id"], unique=False)
    op.create_index("ix_medical_reports_appointment_id", "medical_reports", ["appointment_id"], unique=False)
    op.create_index("ix_medical_reports_conversation_id", "medical_reports", ["conversation_id"], unique=False)

    # 5. patient_allergies
    op.create_table(
        "patient_allergies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_user_id", sa.Integer(), nullable=False),
        sa.Column("allergen_or_condition", sa.String(length=180), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False, server_default="allergy"),
        sa.Column("severity", sa.String(length=30), nullable=False, server_default="mild"),
        sa.Column("reaction", sa.Text(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["patient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_patient_allergies_patient_user_id", "patient_allergies", ["patient_user_id"], unique=False)

    # 6. medical_documents
    op.create_table(
        "medical_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_user_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=60), nullable=False, server_default="other"),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("mime_type", sa.String(length=100), nullable=False, server_default="application/pdf"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("extracted_data", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["patient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_medical_documents_patient_user_id", "medical_documents", ["patient_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_medical_documents_patient_user_id", table_name="medical_documents")
    op.drop_table("medical_documents")

    op.drop_index("ix_patient_allergies_patient_user_id", table_name="patient_allergies")
    op.drop_table("patient_allergies")

    op.drop_index("ix_medical_reports_conversation_id", table_name="medical_reports")
    op.drop_index("ix_medical_reports_appointment_id", table_name="medical_reports")
    op.drop_index("ix_medical_reports_doctor_id", table_name="medical_reports")
    op.drop_index("ix_medical_reports_patient_user_id", table_name="medical_reports")
    op.drop_index("ix_medical_reports_report_id", table_name="medical_reports")
    op.drop_table("medical_reports")

    op.drop_index("ix_prescription_items_prescription_id", table_name="prescription_items")
    op.drop_table("prescription_items")

    op.drop_index("ix_prescriptions_appointment_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_doctor_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_patient_user_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_prescription_number", table_name="prescriptions")
    op.drop_table("prescriptions")

    op.drop_index("ix_clinical_notes_appointment_id", table_name="clinical_notes")
    op.drop_index("ix_clinical_notes_doctor_id", table_name="clinical_notes")
    op.drop_index("ix_clinical_notes_patient_user_id", table_name="clinical_notes")
    op.drop_table("clinical_notes")
