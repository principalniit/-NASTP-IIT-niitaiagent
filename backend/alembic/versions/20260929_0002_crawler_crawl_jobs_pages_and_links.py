"""crawler: crawl jobs, pages and links

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29 09:39:56.270553
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table('crawl_jobs',
    sa.Column('organisation_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('requested_by_id', sa.Uuid(), nullable=True),
    sa.Column('status', sa.Enum('queued', 'running', 'cancelling', 'completed', 'failed', 'cancelled', name='crawl_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('incremental', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('previous_crawl_id', sa.Uuid(), nullable=True),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('pages_discovered', sa.Integer(), server_default='0', nullable=False),
    sa.Column('pages_crawled', sa.Integer(), server_default='0', nullable=False),
    sa.Column('pages_failed', sa.Integer(), server_default='0', nullable=False),
    sa.Column('pages_blocked', sa.Integer(), server_default='0', nullable=False),
    sa.Column('robots_status', sa.String(length=32), nullable=True),
    sa.Column('sitemaps', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('sitemap_url_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('worker_id', sa.String(length=100), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], name=op.f('fk_crawl_jobs_organisation_id_organisations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['previous_crawl_id'], ['crawl_jobs.id'], name=op.f('fk_crawl_jobs_previous_crawl_id_crawl_jobs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_crawl_jobs_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requested_by_id'], ['users.id'], name=op.f('fk_crawl_jobs_requested_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_crawl_jobs'))
    )
    op.create_index(op.f('ix_crawl_jobs_organisation_id'), 'crawl_jobs', ['organisation_id'], unique=False)
    op.create_index('ix_crawl_jobs_project_created', 'crawl_jobs', ['project_id', 'created_at'], unique=False)
    op.create_index('ix_crawl_jobs_status_created', 'crawl_jobs', ['status', 'created_at'], unique=False)
    op.create_index('uq_crawl_jobs_one_active_per_project', 'crawl_jobs', ['project_id'], unique=True, postgresql_where=sa.text("status IN ('queued', 'running', 'cancelling')"))
    op.create_table('crawl_pages',
    sa.Column('organisation_id', sa.Uuid(), nullable=False),
    sa.Column('crawl_job_id', sa.Uuid(), nullable=False),
    sa.Column('url', sa.String(length=2048), nullable=False),
    sa.Column('final_url', sa.String(length=2048), nullable=True),
    sa.Column('depth', sa.Integer(), nullable=True),
    sa.Column('discovered_via', sa.String(length=16), nullable=False),
    sa.Column('fetch_status', sa.Enum('fetched', 'not_modified', 'blocked_by_robots', 'blocked_destination', 'redirect_out_of_scope', 'skipped_content_type', 'too_large', 'error', name='fetch_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('status_code', sa.Integer(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('content_type', sa.String(length=200), nullable=True),
    sa.Column('response_time_ms', sa.Integer(), nullable=True),
    sa.Column('content_length', sa.Integer(), nullable=True),
    sa.Column('redirect_chain', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('etag', sa.String(length=300), nullable=True),
    sa.Column('last_modified', sa.String(length=100), nullable=True),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('title_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('meta_description', sa.Text(), nullable=True),
    sa.Column('meta_description_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('meta_robots', sa.String(length=300), nullable=True),
    sa.Column('x_robots_tag', sa.String(length=300), nullable=True),
    sa.Column('is_noindex', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('is_nofollow', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('canonical_url', sa.String(length=2048), nullable=True),
    sa.Column('canonical_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('lang', sa.String(length=35), nullable=True),
    sa.Column('headings', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('h1_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('word_count', sa.Integer(), nullable=True),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('images', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('image_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('images_missing_alt', sa.Integer(), server_default='0', nullable=False),
    sa.Column('structured_data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('hreflang', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('internal_links_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('external_links_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('inlinks_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('in_sitemap', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('is_orphan', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['crawl_job_id'], ['crawl_jobs.id'], name=op.f('fk_crawl_pages_crawl_job_id_crawl_jobs'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], name=op.f('fk_crawl_pages_organisation_id_organisations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_crawl_pages')),
    sa.UniqueConstraint('crawl_job_id', 'url', name=op.f('uq_crawl_pages_crawl_job_id'))
    )
    op.create_index(op.f('ix_crawl_pages_crawl_job_id'), 'crawl_pages', ['crawl_job_id'], unique=False)
    op.create_index('ix_crawl_pages_job_hash', 'crawl_pages', ['crawl_job_id', 'content_hash'], unique=False)
    op.create_index('ix_crawl_pages_job_status', 'crawl_pages', ['crawl_job_id', 'status_code'], unique=False)
    op.create_index(op.f('ix_crawl_pages_organisation_id'), 'crawl_pages', ['organisation_id'], unique=False)
    op.create_table('crawl_links',
    sa.Column('organisation_id', sa.Uuid(), nullable=False),
    sa.Column('crawl_job_id', sa.Uuid(), nullable=False),
    sa.Column('source_page_id', sa.Uuid(), nullable=False),
    sa.Column('target_url', sa.String(length=2048), nullable=False),
    sa.Column('target_page_id', sa.Uuid(), nullable=True),
    sa.Column('is_internal', sa.Boolean(), nullable=False),
    sa.Column('nofollow', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('anchor_text', sa.String(length=300), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['crawl_job_id'], ['crawl_jobs.id'], name=op.f('fk_crawl_links_crawl_job_id_crawl_jobs'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], name=op.f('fk_crawl_links_organisation_id_organisations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_page_id'], ['crawl_pages.id'], name=op.f('fk_crawl_links_source_page_id_crawl_pages'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['target_page_id'], ['crawl_pages.id'], name=op.f('fk_crawl_links_target_page_id_crawl_pages'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_crawl_links'))
    )
    op.create_index(op.f('ix_crawl_links_crawl_job_id'), 'crawl_links', ['crawl_job_id'], unique=False)
    op.create_index('ix_crawl_links_job_target', 'crawl_links', ['crawl_job_id', 'target_url'], unique=False)
    op.create_index(op.f('ix_crawl_links_organisation_id'), 'crawl_links', ['organisation_id'], unique=False)
    op.create_index(op.f('ix_crawl_links_source_page_id'), 'crawl_links', ['source_page_id'], unique=False)
    op.create_index(op.f('ix_crawl_links_target_page_id'), 'crawl_links', ['target_page_id'], unique=False)



def downgrade() -> None:

    op.drop_index(op.f('ix_crawl_links_target_page_id'), table_name='crawl_links')
    op.drop_index(op.f('ix_crawl_links_source_page_id'), table_name='crawl_links')
    op.drop_index(op.f('ix_crawl_links_organisation_id'), table_name='crawl_links')
    op.drop_index('ix_crawl_links_job_target', table_name='crawl_links')
    op.drop_index(op.f('ix_crawl_links_crawl_job_id'), table_name='crawl_links')
    op.drop_table('crawl_links')
    op.drop_index(op.f('ix_crawl_pages_organisation_id'), table_name='crawl_pages')
    op.drop_index('ix_crawl_pages_job_status', table_name='crawl_pages')
    op.drop_index('ix_crawl_pages_job_hash', table_name='crawl_pages')
    op.drop_index(op.f('ix_crawl_pages_crawl_job_id'), table_name='crawl_pages')
    op.drop_table('crawl_pages')
    op.drop_index('uq_crawl_jobs_one_active_per_project', table_name='crawl_jobs', postgresql_where=sa.text("status IN ('queued', 'running', 'cancelling')"))
    op.drop_index('ix_crawl_jobs_status_created', table_name='crawl_jobs')
    op.drop_index('ix_crawl_jobs_project_created', table_name='crawl_jobs')
    op.drop_index(op.f('ix_crawl_jobs_organisation_id'), table_name='crawl_jobs')
    op.drop_table('crawl_jobs')

