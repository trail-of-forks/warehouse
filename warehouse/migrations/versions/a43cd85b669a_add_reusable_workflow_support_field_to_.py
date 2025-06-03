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
Add reusable workflow support field to GH Trusted Publishers

Revision ID: a43cd85b669a
Revises: 082def83d89f
Create Date: 2025-05-22 17:46:57.516459
"""

import sqlalchemy as sa

from alembic import op

revision = "a43cd85b669a"
down_revision = "082def83d89f"


def upgrade():
    op.add_column(
        "github_oidc_publishers",
        sa.Column(
            "supports_legacy_reusable_workflows",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("github_oidc_publishers", "supports_legacy_reusable_workflows")
