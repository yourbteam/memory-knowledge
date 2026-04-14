import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, text

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override URL from environment variable
url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url", ""))


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=None, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(url)
    with connectable.connect() as connection:
        # Alembic defaults version_num to VARCHAR(32), but this repo uses
        # descriptive revision ids that are longer than 32 characters.
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS alembic_version (
                    version_num VARCHAR(255) NOT NULL PRIMARY KEY
                )
                """
            )
        )
        connection.execute(
            text(
                """
                ALTER TABLE alembic_version
                ALTER COLUMN version_num TYPE VARCHAR(255)
                """
            )
        )
        connection.commit()
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
