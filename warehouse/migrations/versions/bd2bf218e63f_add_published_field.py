# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
add published field

Revision ID: bd2bf218e63f
Revises: f7720656a33c
Create Date: 2024-12-10 10:40:19.588606
"""

import sqlalchemy as sa

from alembic import op

revision = "bd2bf218e63f"
down_revision = "f7720656a33c"


def upgrade():
    op.add_column(
        "releases",
        sa.Column(
            "published", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("releases", "published")