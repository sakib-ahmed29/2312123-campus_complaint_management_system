"""Create multi-user CampusCare schema and attach legacy complaints to owners."""
from alembic import op
import sqlalchemy as sa
import main

revision = "0001_secure_multiuser"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # Create new tables first. Existing MVP complaint tables are left intact.
    main.SQLModel.metadata.create_all(bind=bind, checkfirst=True)
    inspector = sa.inspect(bind)
    if "complaint" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("complaint")}
        if "owner_id" not in columns:
            op.add_column("complaint", sa.Column("owner_id", sa.String(length=36),
                                                sa.ForeignKey("user.id"), nullable=True))
            op.create_index("ix_complaint_owner_id", "complaint", ["owner_id"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "complaint" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("complaint")}
        if "owner_id" in columns:
            try:
                op.drop_index("ix_complaint_owner_id", table_name="complaint")
            except Exception:
                pass
            with op.batch_alter_table("complaint") as batch:
                batch.drop_column("owner_id")
