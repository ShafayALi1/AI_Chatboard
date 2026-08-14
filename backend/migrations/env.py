from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import create_engine

from dotenv import load_dotenv
from backend.models import Base


# Load variables from .env
load_dotenv()


# Alembic configuration object
config = context.config


# Configure Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# SQLAlchemy models
# Alembic uses this to detect changes in our models
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations without creating a database connection.
    """

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL not found")

    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations using a real database connection.
    """

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL not found")

    # Create SQLAlchemy engine using Neon DATABASE_URL
    connectable = create_engine(database_url)

    with connectable.connect() as connection:

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()