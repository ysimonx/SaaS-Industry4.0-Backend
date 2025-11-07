"""Add SSO support

Revision ID: add_sso_support
Revises:
Create Date: 2025-01-05 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_sso_support'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create TenantSSOConfig table
    op.create_table('tenant_sso_configs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('client_id', sa.String(length=255), nullable=False),
        sa.Column('provider_tenant_id', sa.String(length=255), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('config_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tenant_sso_configs_client_id'), 'tenant_sso_configs', ['client_id'], unique=False)
    op.create_index(op.f('ix_tenant_sso_configs_provider'), 'tenant_sso_configs', ['provider'], unique=False)
    op.create_index(op.f('ix_tenant_sso_configs_tenant_id'), 'tenant_sso_configs', ['tenant_id'], unique=True)

    # Create UserAzureIdentity table
    op.create_table('user_azure_identities',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('azure_object_id', sa.String(length=255), nullable=False),
        sa.Column('azure_upn', sa.String(length=255), nullable=True),
        sa.Column('azure_display_name', sa.String(length=255), nullable=True),
        sa.Column('refresh_token_encrypted', sa.Text(), nullable=True),
        sa.Column('access_token_encrypted', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(), nullable=True),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'tenant_id', name='uq_user_tenant_azure')
    )
    op.create_index(op.f('ix_user_azure_identities_azure_object_id'), 'user_azure_identities', ['azure_object_id'], unique=False)
    op.create_index(op.f('ix_user_azure_identities_azure_upn'), 'user_azure_identities', ['azure_upn'], unique=False)
    op.create_index(op.f('ix_user_azure_identities_tenant_id'), 'user_azure_identities', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_user_azure_identities_user_id'), 'user_azure_identities', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_azure_identities_token_expires_at'), 'user_azure_identities', ['token_expires_at'], unique=False)

    # Add SSO-related columns to tenants table
    with op.batch_alter_table('tenants') as batch_op:
        batch_op.add_column(sa.Column('auth_method', sa.String(length=20), nullable=False, server_default='local'))
        batch_op.add_column(sa.Column('sso_domain_whitelist', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('auto_provisioning_enabled', sa.Boolean(), nullable=False, server_default='false'))

    # Add SSO-related columns to users table
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('sso_provider', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('last_sso_login', sa.DateTime(), nullable=True))
        # Make password nullable for SSO-only users
        batch_op.alter_column('password_hash',
                              existing_type=sa.String(length=255),
                              nullable=True)

    # Create indexes for new columns
    op.create_index(op.f('ix_tenants_auth_method'), 'tenants', ['auth_method'], unique=False)
    op.create_index(op.f('ix_users_sso_provider'), 'users', ['sso_provider'], unique=False)


def downgrade():
    # Remove indexes
    op.drop_index(op.f('ix_users_sso_provider'), table_name='users')
    op.drop_index(op.f('ix_tenants_auth_method'), table_name='tenants')

    # Remove SSO columns from users table
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('password_hash',
                              existing_type=sa.String(length=255),
                              nullable=False)
        batch_op.drop_column('last_sso_login')
        batch_op.drop_column('sso_provider')

    # Remove SSO columns from tenants table
    with op.batch_alter_table('tenants') as batch_op:
        batch_op.drop_column('auto_provisioning_enabled')
        batch_op.drop_column('sso_domain_whitelist')
        batch_op.drop_column('auth_method')

    # Drop indexes for UserAzureIdentity
    op.drop_index(op.f('ix_user_azure_identities_token_expires_at'), table_name='user_azure_identities')
    op.drop_index(op.f('ix_user_azure_identities_user_id'), table_name='user_azure_identities')
    op.drop_index(op.f('ix_user_azure_identities_tenant_id'), table_name='user_azure_identities')
    op.drop_index(op.f('ix_user_azure_identities_azure_upn'), table_name='user_azure_identities')
    op.drop_index(op.f('ix_user_azure_identities_azure_object_id'), table_name='user_azure_identities')

    # Drop UserAzureIdentity table
    op.drop_table('user_azure_identities')

    # Drop indexes for TenantSSOConfig
    op.drop_index(op.f('ix_tenant_sso_configs_tenant_id'), table_name='tenant_sso_configs')
    op.drop_index(op.f('ix_tenant_sso_configs_provider'), table_name='tenant_sso_configs')
    op.drop_index(op.f('ix_tenant_sso_configs_client_id'), table_name='tenant_sso_configs')

    # Drop TenantSSOConfig table
    op.drop_table('tenant_sso_configs')