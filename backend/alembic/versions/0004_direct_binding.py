"""Non-secret Yandex Direct project binding and auditable changes.

Revision ID: 0004_direct_binding
Revises: 0003_project_events
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_direct_binding"
down_revision = "0003_project_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_direct_bindings",
        sa.Column("project_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("client_login", sa.String(255), nullable=False),
        sa.Column(
            "status", sa.String(32), nullable=False,
            server_default=sa.text("'configured_unverified'"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_direct_bindings_project_org",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "client_login ~ '^[A-Za-z0-9][A-Za-z0-9._@-]{0,254}$'",
            name="ck_direct_bindings_login",
        ),
        sa.CheckConstraint(
            "status = 'configured_unverified'",
            name="ck_direct_bindings_status",
        ),
    )

    op.add_column("project_events", sa.Column("old_client_login", sa.String(255)))
    op.add_column("project_events", sa.Column("new_client_login", sa.String(255)))
    op.drop_constraint("ck_project_events_action", "project_events", type_="check")
    op.create_check_constraint(
        "ck_project_events_action", "project_events",
        "action IN ('rename', 'archive', 'restore', 'direct_bind', 'direct_unbind')",
    )


def downgrade() -> None:
    # DESTRUCTIVE: dropping this revision discards project bindings and logins
    # in existing append-only audit rows. Do not downgrade a working database.
    op.drop_constraint("ck_project_events_action", "project_events", type_="check")
    op.create_check_constraint(
        "ck_project_events_action", "project_events",
        "action IN ('rename', 'archive', 'restore')",
    )
    op.drop_column("project_events", "new_client_login")
    op.drop_column("project_events", "old_client_login")
    op.drop_table("project_direct_bindings")
