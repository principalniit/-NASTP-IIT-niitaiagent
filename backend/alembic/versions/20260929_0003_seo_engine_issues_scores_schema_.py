"""seo engine: issues, scores, schema findings, link recommendations

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29 10:23:24.510806
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table('seo_issues',
    sa.Column('organisation_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('issue_key', sa.String(length=200), nullable=False),
    sa.Column('rule_id', sa.String(length=80), nullable=False),
    sa.Column('scope', sa.String(length=8), nullable=False),
    sa.Column('category', sa.Enum('technical', 'on_page', 'content', 'internal_linking', 'structured_data', name='seo_category', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('severity', sa.Enum('critical', 'high', 'medium', 'low', 'informational', name='seo_severity', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('recommendation', sa.Text(), nullable=False),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('affected_url', sa.String(length=2048), nullable=True),
    sa.Column('affected_urls', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('affected_page_count', sa.Integer(), nullable=False),
    sa.Column('confidence', sa.String(length=16), nullable=False),
    sa.Column('effort', sa.String(length=16), nullable=False),
    sa.Column('priority_score', sa.Float(), nullable=False),
    sa.Column('priority_breakdown', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('auto_fix_eligible', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('approval_status', sa.Enum('none', 'pending_review', 'approved', 'rejected', name='seo_approval_status', native_enum=False, create_constraint=True, length=32), server_default='none', nullable=False),
    sa.Column('resolution_status', sa.Enum('open', 'resolved', 'ignored', name='seo_resolution_status', native_enum=False, create_constraint=True, length=32), server_default='open', nullable=False),
    sa.Column('first_detected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_detected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('first_crawl_id', sa.Uuid(), nullable=True),
    sa.Column('last_crawl_id', sa.Uuid(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_in_crawl_id', sa.Uuid(), nullable=True),
    sa.Column('recurrence_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('triage_note', sa.String(length=1000), nullable=True),
    sa.Column('triaged_by_id', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['first_crawl_id'], ['crawl_jobs.id'], name=op.f('fk_seo_issues_first_crawl_id_crawl_jobs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['last_crawl_id'], ['crawl_jobs.id'], name=op.f('fk_seo_issues_last_crawl_id_crawl_jobs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], name=op.f('fk_seo_issues_organisation_id_organisations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_seo_issues_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['resolved_in_crawl_id'], ['crawl_jobs.id'], name=op.f('fk_seo_issues_resolved_in_crawl_id_crawl_jobs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['triaged_by_id'], ['users.id'], name=op.f('fk_seo_issues_triaged_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_seo_issues')),
    sa.UniqueConstraint('project_id', 'issue_key', name=op.f('uq_seo_issues_project_id'))
    )
    op.create_index(op.f('ix_seo_issues_last_crawl_id'), 'seo_issues', ['last_crawl_id'], unique=False)
    op.create_index(op.f('ix_seo_issues_organisation_id'), 'seo_issues', ['organisation_id'], unique=False)
    op.create_index('ix_seo_issues_project_status_priority', 'seo_issues', ['project_id', 'resolution_status', 'priority_score'], unique=False)
    op.create_index(op.f('ix_seo_issues_rule_id'), 'seo_issues', ['rule_id'], unique=False)
    op.create_table('seo_scores',
    sa.Column('organisation_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('crawl_job_id', sa.Uuid(), nullable=False),
    sa.Column('overall', sa.Float(), nullable=True),
    sa.Column('technical', sa.Float(), nullable=True),
    sa.Column('on_page', sa.Float(), nullable=True),
    sa.Column('content', sa.Float(), nullable=True),
    sa.Column('internal_linking', sa.Float(), nullable=True),
    sa.Column('structured_data', sa.Float(), nullable=True),
    sa.Column('pages_analysed', sa.Integer(), nullable=False),
    sa.Column('breakdown', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['crawl_job_id'], ['crawl_jobs.id'], name=op.f('fk_seo_scores_crawl_job_id_crawl_jobs'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], name=op.f('fk_seo_scores_organisation_id_organisations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_seo_scores_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_seo_scores')),
    sa.UniqueConstraint('crawl_job_id', name=op.f('uq_seo_scores_crawl_job_id'))
    )
    op.create_index(op.f('ix_seo_scores_organisation_id'), 'seo_scores', ['organisation_id'], unique=False)
    op.create_index(op.f('ix_seo_scores_project_id'), 'seo_scores', ['project_id'], unique=False)
    op.create_table('internal_link_recommendations',
    sa.Column('organisation_id', sa.Uuid(), nullable=False),
    sa.Column('crawl_job_id', sa.Uuid(), nullable=False),
    sa.Column('source_page_id', sa.Uuid(), nullable=False),
    sa.Column('target_page_id', sa.Uuid(), nullable=False),
    sa.Column('anchor_text', sa.String(length=300), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('relevance', sa.Float(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['crawl_job_id'], ['crawl_jobs.id'], name=op.f('fk_internal_link_recommendations_crawl_job_id_crawl_jobs'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], name=op.f('fk_internal_link_recommendations_organisation_id_organisations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_page_id'], ['crawl_pages.id'], name=op.f('fk_internal_link_recommendations_source_page_id_crawl_pages'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['target_page_id'], ['crawl_pages.id'], name=op.f('fk_internal_link_recommendations_target_page_id_crawl_pages'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_internal_link_recommendations'))
    )
    op.create_index(op.f('ix_internal_link_recommendations_crawl_job_id'), 'internal_link_recommendations', ['crawl_job_id'], unique=False)
    op.create_index(op.f('ix_internal_link_recommendations_organisation_id'), 'internal_link_recommendations', ['organisation_id'], unique=False)
    op.create_table('schema_findings',
    sa.Column('organisation_id', sa.Uuid(), nullable=False),
    sa.Column('crawl_job_id', sa.Uuid(), nullable=False),
    sa.Column('page_id', sa.Uuid(), nullable=False),
    sa.Column('format', sa.String(length=16), nullable=False),
    sa.Column('schema_types', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_valid', sa.Boolean(), nullable=False),
    sa.Column('errors', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['crawl_job_id'], ['crawl_jobs.id'], name=op.f('fk_schema_findings_crawl_job_id_crawl_jobs'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], name=op.f('fk_schema_findings_organisation_id_organisations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['page_id'], ['crawl_pages.id'], name=op.f('fk_schema_findings_page_id_crawl_pages'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_schema_findings'))
    )
    op.create_index(op.f('ix_schema_findings_crawl_job_id'), 'schema_findings', ['crawl_job_id'], unique=False)
    op.create_index(op.f('ix_schema_findings_organisation_id'), 'schema_findings', ['organisation_id'], unique=False)
    op.create_index(op.f('ix_schema_findings_page_id'), 'schema_findings', ['page_id'], unique=False)
    op.add_column('crawl_jobs', sa.Column('analysis_status', sa.Enum('none', 'queued', 'running', 'completed', 'failed', name='analysis_status', native_enum=False, create_constraint=True, length=32), server_default='none', nullable=False))
    op.add_column('crawl_jobs', sa.Column('analysed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('crawl_jobs', sa.Column('analysis_error', sa.Text(), nullable=True))
    op.add_column('crawl_pages', sa.Column('text_content', sa.Text(), nullable=True))



def downgrade() -> None:

    op.drop_column('crawl_pages', 'text_content')
    op.drop_column('crawl_jobs', 'analysis_error')
    op.drop_column('crawl_jobs', 'analysed_at')
    op.drop_column('crawl_jobs', 'analysis_status')
    op.drop_index(op.f('ix_schema_findings_page_id'), table_name='schema_findings')
    op.drop_index(op.f('ix_schema_findings_organisation_id'), table_name='schema_findings')
    op.drop_index(op.f('ix_schema_findings_crawl_job_id'), table_name='schema_findings')
    op.drop_table('schema_findings')
    op.drop_index(op.f('ix_internal_link_recommendations_organisation_id'), table_name='internal_link_recommendations')
    op.drop_index(op.f('ix_internal_link_recommendations_crawl_job_id'), table_name='internal_link_recommendations')
    op.drop_table('internal_link_recommendations')
    op.drop_index(op.f('ix_seo_scores_project_id'), table_name='seo_scores')
    op.drop_index(op.f('ix_seo_scores_organisation_id'), table_name='seo_scores')
    op.drop_table('seo_scores')
    op.drop_index(op.f('ix_seo_issues_rule_id'), table_name='seo_issues')
    op.drop_index('ix_seo_issues_project_status_priority', table_name='seo_issues')
    op.drop_index(op.f('ix_seo_issues_organisation_id'), table_name='seo_issues')
    op.drop_index(op.f('ix_seo_issues_last_crawl_id'), table_name='seo_issues')
    op.drop_table('seo_issues')

