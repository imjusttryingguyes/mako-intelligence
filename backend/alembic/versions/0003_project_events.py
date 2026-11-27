"""Reversible project status and append-only project change audit.

Revision ID: 0003_project_events
Revises: 0002_local_auth
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_project_events"
down_revision = "0002_local_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_events",
        sa.Column("id", sa.Uuid(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("old_name", sa.String(200), nullable=True),
        sa.Column("new_name", sa.String(200), nullable=True),
        sa.Column("old_status", sa.String(20), nullable=True),
        sa.Column("new_status", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"], ["projects.organization_id", "projects.id"],
            name="fk_project_events_project_org", ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "action IN ('rename', 'archive', 'restore')",
            name="ck_project_events_action",
        ),
    )
    op.create_index(
        "ix_project_events_org_project_created",
        "project_events", ["organization_id", "project_id", "created_at"],
    )
    # Even direct SQL connections must not rewrite or erase existing audit rows.
    # A privileged database owner can change the trigger; production requires
    # separate write roles, backups and external log integrity verification.
    op.execute("""
        CREATE FUNCTION mako_deny_project_event_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'project audit events are append-only';
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_project_events_append_only
        BEFORE UPDATE OR DELETE ON project_events
        FOR EACH ROW EXECUTE FUNCTION mako_deny_project_event_mutation();
    """)


def downgrade() -> None:
    # Downgrade is destructive for audit history; never use it on a real dataset.
    op.drop_table("project_events")
    op.execute("DROP FUNCTION mako_deny_project_event_mutation()")
