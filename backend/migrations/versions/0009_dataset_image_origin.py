"""dataset image origin: where the images came from

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-18

Expand-only. A publisher's licence only covers images the publisher had the right to license, so approval now needs the
origin of the images to be recorded (publisher_created or third_party_licensed). Existing rows default to 'unknown'.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

ORIGINS = "'publisher_created', 'third_party_licensed', 'third_party_scraped', 'unknown'"


def upgrade() -> None:
    with op.batch_alter_table("datasets") as batch:
        batch.add_column(sa.Column("image_origin", sa.String(length=24), nullable=False, server_default="unknown"))
        batch.create_check_constraint(op.f("ck_datasets_image_origin"), f"image_origin IN ({ORIGINS})")


def downgrade() -> None:
    with op.batch_alter_table("datasets") as batch:
        batch.drop_constraint(op.f("ck_datasets_image_origin"), type_="check")
        batch.drop_column("image_origin")
