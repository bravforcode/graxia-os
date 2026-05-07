"""
ULTRA Migration: Audit Logs and Enhanced Base Model
Add comprehensive audit logging and security tables

Revision ID: 003
Revises: 002
Create Date: 2026-05-05 00:00:00.000000+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: str | None = '002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    ULTRA Upgrade:
    1. Create audit_log table
    2. Create security_event table
    3. Create failed_login_attempt table
    4. Add audit columns to existing tables
    """

    # Create audit_log table
    op.create_table(
        'audit_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('organization.id', ondelete='CASCADE'),
                  nullable=True, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('user.id', ondelete='SET NULL'),
                  nullable=True, index=True),
        sa.Column('action', sa.String(100), nullable=False, index=True),
        sa.Column('resource_type', sa.String(50), nullable=False),
        sa.Column('resource_id', sa.String(100), nullable=True),
        sa.Column('before_data', postgresql.JSONB, nullable=True),
        sa.Column('after_data', postgresql.JSONB, nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('request_id', sa.String(36), nullable=True, index=True),
        sa.Column('is_sensitive', sa.Boolean, default=False, index=True),
        sa.Column('severity', sa.String(20), default='info'),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('user.id', ondelete='SET NULL'),
                  nullable=True, index=True),
    )

    # Composite indexes for audit_log
    op.create_index(
        'idx_audit_org_action_time',
        'audit_log',
        ['organization_id', 'action', 'created_at']
    )
    op.create_index(
        'idx_audit_user_time',
        'audit_log',
        ['user_id', 'created_at']
    )
    op.create_index(
        'idx_audit_resource',
        'audit_log',
        ['resource_type', 'resource_id']
    )
    op.create_index(
        'idx_audit_sensitive',
        'audit_log',
        ['is_sensitive', 'created_at']
    )

    # Create security_event table
    op.create_table(
        'security_event',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('organization.id', ondelete='CASCADE'),
                  nullable=True, index=True),
        sa.Column('event_type', sa.String(50), nullable=False, index=True),
        sa.Column('severity', sa.String(20), nullable=False, default='low'),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('user.id', ondelete='SET NULL'),
                  nullable=True, index=True),
        sa.Column('ip_address', sa.String(45), nullable=False, index=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('raw_data', postgresql.JSONB, nullable=True),
        sa.Column('is_resolved', sa.Boolean, default=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('user.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('resolution_notes', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('user.id', ondelete='SET NULL'),
                  nullable=True),
    )

    # Composite indexes for security_event
    op.create_index(
        'idx_security_event_type_severity',
        'security_event',
        ['event_type', 'severity']
    )
    op.create_index(
        'idx_security_ip_time',
        'security_event',
        ['ip_address', 'created_at']
    )
    op.create_index(
        'idx_security_unresolved',
        'security_event',
        ['is_resolved', 'severity']
    )

    # Create failed_login_attempt table
    op.create_table(
        'failed_login_attempt',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('email', sa.String(255), nullable=False, index=True),
        sa.Column('ip_address', sa.String(45), nullable=False, index=True),
        sa.Column('attempted_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False, index=True),
        sa.Column('failure_reason', sa.String(100), nullable=False),
        sa.Column('country_code', sa.String(2), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('device_fingerprint', sa.String(64), nullable=True, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # Composite indexes for failed_login_attempt
    op.create_index(
        'idx_failed_login_email_time',
        'failed_login_attempt',
        ['email', 'attempted_at']
    )
    op.create_index(
        'idx_failed_login_ip_time',
        'failed_login_attempt',
        ['ip_address', 'attempted_at']
    )

    # Add updated_by_id to existing tables that need it
    tables_with_audit = [
        'user', 'organization', 'contact', 'opportunity',
        'submission', 'job_posting', 'email_thread', 'usage_log'
    ]

    for table in tables_with_audit:
        # Check if column exists first
        conn = op.get_bind()
        inspector = sa.inspect(conn)
        columns = inspector.get_columns(table)
        column_names = [col['name'] for col in columns]

        if 'updated_by_id' not in column_names:
            op.add_column(
                table,
                sa.Column('updated_by_id', postgresql.UUID(as_uuid=True),
                         sa.ForeignKey('user.id', ondelete='SET NULL'),
                         nullable=True, index=True)
            )


def downgrade() -> None:
    """
    ULTRA Downgrade:
    Remove audit tables (with warning - data loss)
    """
    # Drop audit tables
    op.drop_table('failed_login_attempt')
    op.drop_table('security_event')
    op.drop_table('audit_log')

    # Remove updated_by_id from tables
    tables_with_audit = [
        'user', 'organization', 'contact', 'opportunity',
        'submission', 'job_posting', 'email_thread', 'usage_log'
    ]

    for table in tables_with_audit:
        conn = op.get_bind()
        inspector = sa.inspect(conn)
        columns = inspector.get_columns(table)
        column_names = [col['name'] for col in columns]

        if 'updated_by_id' in column_names:
            op.drop_column(table, 'updated_by_id')
