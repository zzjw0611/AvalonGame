"""Initial durable guest sessions and room snapshots."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('guests',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('name', sa.String(32), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=False))
    op.create_index('ix_guests_token_hash', 'guests', ['token_hash'], unique=True)
    op.create_table('rooms',
        sa.Column('code', sa.String(8), primary_key=True),
        sa.Column('host_id', sa.String(32), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=False),
        sa.Column('state', sa.JSON(), nullable=False))
    op.create_index('ix_rooms_host_id', 'rooms', ['host_id'])
    op.create_index('ix_rooms_status', 'rooms', ['status'])


def downgrade():
    op.drop_table('rooms')
    op.drop_table('guests')
