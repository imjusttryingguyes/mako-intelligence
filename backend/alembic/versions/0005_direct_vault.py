"""Encrypted local agency credentials and last verified account metadata.

Revision ID: 0005_direct_vault
Revises: 0004_direct_binding
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_direct_vault"
down_revision = "0004_direct_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_direct_credentials",
        sa.Column(
            "organization_id", sa.Uuid(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True,
        ),
        sa.Column("encrypted_token", sa.LargeBinary(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("revision > 0", name="ck_direct_credentials_revision"),
        sa.CheckConstraint(
            "octet_length(encrypted_token) >= 30",
            name="ck_direct_credentials_ciphertext",
        ),
    )
    op.add_column(
        "project_direct_bindings",
        sa.Column("verified_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "project_direct_bindings",
        sa.Column("verified_token_revision", sa.Integer()),
    )
    op.add_column(
        "project_direct_bindings",
        sa.Column("verified_campaign_count", sa.Integer()),
    )


def downgrade() -> None:
    # DESTRUCTIVE: drops encrypted credentials and verification metadata.
    # Do not downgrade a working installation.
    op.drop_column("project_direct_bindings", "verified_campaign_count")
    op.drop_column("project_direct_bindings", "verified_token_revision")
    op.drop_column("project_direct_bindings", "verified_at")
    op.drop_table("organization_direct_credentials")
