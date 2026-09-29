"""ai analyses, recommendations, content drafts and approvals

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-29 10:57:58.914537
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table('ai_analyses',
    sa.Column('organisation_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('crawl_job_id', sa.Uuid(), nullable=True),
    sa.Column('kind', sa.Enum('management_summary', 'issue_explanation', 'page_plan', 'metadata_draft', 'content_outline', 'question', name='ai_kind', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('status', sa.Enum('queued', 'running', 'completed', 'failed', name='ai_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('subject_type', sa.String(length=20), nullable=False),
    sa.Column('subject_id', sa.String(length=64), nullable=True),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=True),
    sa.Column('model', sa.String(length=100), nullable=True),
    sa.Column('prompt_version', sa.String(length=20), nullable=True),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('output', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('grounding', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('requested_by_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['crawl_job_id'], ['crawl_jobs.id'], name=op.f('fk_ai_analyses_crawl_job_id_crawl_jobs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], name=op.f('fk_ai_analyses_organisation_id_organisations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_ai_analyses_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requested_by_id'], ['users.id'], name=op.f('fk_ai_analyses_requested_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_analyses'))
    )
    op.create_index(op.f('ix_ai_analyses_organisation_id'), 'ai_analyses', ['organisation_id'], unique=False)
    op.create_index('ix_ai_analyses_project_kind_created', 'ai_analyses', ['project_id', 'kind', 'created_at'], unique=False)
    op.create_index('ix_ai_analyses_status_created', 'ai_analyses', ['status', 'created_at'], unique=False)
    op.create_table('content_drafts',
    sa.Column('organisation_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('page_url', sa.String(length=2048), nullable=False),
    sa.Column('crawl_page_id', sa.Uuid(), nullable=True),
    sa.Column('field', sa.Enum('title', 'meta_description', 'h1', 'content_outline', 'content_section', name='draft_field', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('original_content', sa.Text(), nullable=True),
    sa.Column('proposed_content', sa.Text(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('source', sa.Enum('ai', 'human', name='draft_source', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('ai_analysis_id', sa.Uuid(), nullable=True),
    sa.Column('status', sa.Enum('draft', 'pending_review', 'approved', 'rejected', 'published', 'rolled_back', name='draft_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('protected', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('protected_reasons', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('created_by_id', sa.Uuid(), nullable=True),
    sa.Column('version_author_id', sa.Uuid(), nullable=True),
    sa.Column('reviewed_by_id', sa.Uuid(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source_reference', sa.String(length=2048), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rolled_back_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['ai_analysis_id'], ['ai_analyses.id'], name=op.f('fk_content_drafts_ai_analysis_id_ai_analyses'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['crawl_page_id'], ['crawl_pages.id'], name=op.f('fk_content_drafts_crawl_page_id_crawl_pages'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_content_drafts_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], name=op.f('fk_content_drafts_organisation_id_organisations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_content_drafts_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id'], name=op.f('fk_content_drafts_reviewed_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['version_author_id'], ['users.id'], name=op.f('fk_content_drafts_version_author_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_content_drafts'))
    )
    op.create_index(op.f('ix_content_drafts_organisation_id'), 'content_drafts', ['organisation_id'], unique=False)
    op.create_index('ix_content_drafts_project_status', 'content_drafts', ['project_id', 'status'], unique=False)
    op.create_table('seo_recommendations',
    sa.Column('organisation_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('ai_analysis_id', sa.Uuid(), nullable=False),
    sa.Column('issue_ids', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('page_url', sa.String(length=2048), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('status', sa.Enum('open', 'accepted', 'dismissed', name='recommendation_status', native_enum=False, create_constraint=True, length=32), server_default='open', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['ai_analysis_id'], ['ai_analyses.id'], name=op.f('fk_seo_recommendations_ai_analysis_id_ai_analyses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], name=op.f('fk_seo_recommendations_organisation_id_organisations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_seo_recommendations_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_seo_recommendations'))
    )
    op.create_index(op.f('ix_seo_recommendations_ai_analysis_id'), 'seo_recommendations', ['ai_analysis_id'], unique=False)
    op.create_index(op.f('ix_seo_recommendations_organisation_id'), 'seo_recommendations', ['organisation_id'], unique=False)
    op.create_index(op.f('ix_seo_recommendations_project_id'), 'seo_recommendations', ['project_id'], unique=False)
    op.create_table('approvals',
    sa.Column('organisation_id', sa.Uuid(), nullable=False),
    sa.Column('draft_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('action', sa.Enum('created', 'edited', 'submitted', 'approved', 'rejected', 'reopened', 'published', 'rolled_back', name='approval_action', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('from_status', sa.String(length=32), nullable=True),
    sa.Column('to_status', sa.String(length=32), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('source_reference', sa.String(length=2048), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_approvals_actor_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['draft_id'], ['content_drafts.id'], name=op.f('fk_approvals_draft_id_content_drafts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], name=op.f('fk_approvals_organisation_id_organisations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_approvals'))
    )
    op.create_index(op.f('ix_approvals_draft_id'), 'approvals', ['draft_id'], unique=False)
    op.create_index(op.f('ix_approvals_organisation_id'), 'approvals', ['organisation_id'], unique=False)
    op.create_table('content_draft_versions',
    sa.Column('organisation_id', sa.Uuid(), nullable=False),
    sa.Column('draft_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('proposed_content', sa.Text(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('source', sa.Enum('ai', 'human', name='draft_version_source', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('edited_by_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['draft_id'], ['content_drafts.id'], name=op.f('fk_content_draft_versions_draft_id_content_drafts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['edited_by_id'], ['users.id'], name=op.f('fk_content_draft_versions_edited_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], name=op.f('fk_content_draft_versions_organisation_id_organisations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_content_draft_versions')),
    sa.UniqueConstraint('draft_id', 'version', name=op.f('uq_content_draft_versions_draft_id'))
    )
    op.create_index(op.f('ix_content_draft_versions_draft_id'), 'content_draft_versions', ['draft_id'], unique=False)
    op.create_index(op.f('ix_content_draft_versions_organisation_id'), 'content_draft_versions', ['organisation_id'], unique=False)



def downgrade() -> None:

    op.drop_index(op.f('ix_content_draft_versions_organisation_id'), table_name='content_draft_versions')
    op.drop_index(op.f('ix_content_draft_versions_draft_id'), table_name='content_draft_versions')
    op.drop_table('content_draft_versions')
    op.drop_index(op.f('ix_approvals_organisation_id'), table_name='approvals')
    op.drop_index(op.f('ix_approvals_draft_id'), table_name='approvals')
    op.drop_table('approvals')
    op.drop_index(op.f('ix_seo_recommendations_project_id'), table_name='seo_recommendations')
    op.drop_index(op.f('ix_seo_recommendations_organisation_id'), table_name='seo_recommendations')
    op.drop_index(op.f('ix_seo_recommendations_ai_analysis_id'), table_name='seo_recommendations')
    op.drop_table('seo_recommendations')
    op.drop_index('ix_content_drafts_project_status', table_name='content_drafts')
    op.drop_index(op.f('ix_content_drafts_organisation_id'), table_name='content_drafts')
    op.drop_table('content_drafts')
    op.drop_index('ix_ai_analyses_status_created', table_name='ai_analyses')
    op.drop_index('ix_ai_analyses_project_kind_created', table_name='ai_analyses')
    op.drop_index(op.f('ix_ai_analyses_organisation_id'), table_name='ai_analyses')
    op.drop_table('ai_analyses')

