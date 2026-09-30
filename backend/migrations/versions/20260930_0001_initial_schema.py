"""Initial HR Client schema.

Revision ID: 20260930_0001
Revises:
Create Date: 2026-09-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260930_0001"
down_revision = None
branch_labels = None
depends_on = None

vacancy_source = sa.Enum("HH", "TELEGRAM", name="vacancysource")
application_status = sa.Enum(
    "DRAFT", "APPROVED", "QUEUED", "SENT", "VIEWED", "INVITED", "REJECTED", "FAILED", name="applicationstatus"
)


def audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table("resumes", *audit_columns(), sa.Column("filename", sa.String(255), nullable=False), sa.Column("raw_text", sa.Text(), nullable=False), sa.Column("structured_data", postgresql.JSONB(), nullable=False))
    op.create_table("matching_profiles", *audit_columns(), sa.Column("name", sa.String(120), nullable=False, unique=True), sa.Column("rules", postgresql.JSONB(), nullable=False), sa.Column("custom_prompt", sa.Text(), nullable=True))
    op.create_table("vacancies", *audit_columns(), sa.Column("source", vacancy_source, nullable=False), sa.Column("external_id", sa.String(255), nullable=False), sa.Column("title", sa.String(500), nullable=False), sa.Column("company", sa.String(500), nullable=True), sa.Column("description", sa.Text(), nullable=False), sa.Column("url", sa.String(2048), nullable=False), sa.Column("published_at", sa.DateTime(timezone=True), nullable=False), sa.Column("payload", postgresql.JSONB(), nullable=False), sa.UniqueConstraint("source", "external_id", name="uq_vacancy_source_external"))
    op.create_table("matches", *audit_columns(), sa.Column("vacancy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vacancies.id"), nullable=False), sa.Column("resume_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("resumes.id"), nullable=False), sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("matching_profiles.id"), nullable=False), sa.Column("score", sa.Float(), nullable=False), sa.Column("rationale", sa.Text(), nullable=False), sa.Column("breakdown", postgresql.JSONB(), nullable=False))
    op.create_table("applications", *audit_columns(), sa.Column("vacancy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vacancies.id"), nullable=False), sa.Column("resume_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("resumes.id"), nullable=False), sa.Column("status", application_status, nullable=False), sa.Column("cover_letter", sa.Text(), nullable=False), sa.Column("external_id", sa.String(255), nullable=True))
    op.create_table("application_events", *audit_columns(), sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("applications.id"), nullable=False), sa.Column("status", application_status, nullable=False), sa.Column("detail", postgresql.JSONB(), nullable=False))


def downgrade() -> None:
    op.drop_table("application_events")
    op.drop_table("applications")
    op.drop_table("matches")
    op.drop_table("vacancies")
    op.drop_table("matching_profiles")
    op.drop_table("resumes")
    application_status.drop(op.get_bind(), checkfirst=True)
    vacancy_source.drop(op.get_bind(), checkfirst=True)
