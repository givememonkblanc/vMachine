from collections.abc import Mapping
from contextlib import AbstractContextManager
from importlib import import_module
from logging.config import fileConfig
from typing import Protocol, cast

from sqlalchemy import engine_from_config, pool

from app.core.config.settings import get_settings
from app.db.base import Base


class AlembicConfig(Protocol):
    config_file_name: str | None
    config_ini_section: str

    def set_main_option(self, name: str, value: str) -> None: ...

    def get_main_option(self, name: str) -> str: ...

    def get_section(self, name: str, default: Mapping[str, str]) -> Mapping[str, str]: ...


class AlembicContext(Protocol):
    config: AlembicConfig

    def configure(self, **kwargs: object) -> None: ...

    def begin_transaction(self) -> AbstractContextManager[object]: ...

    def run_migrations(self) -> None: ...

    def is_offline_mode(self) -> bool: ...


context_module = cast(object, import_module("alembic.context"))
context = cast(AlembicContext, context_module)

settings = get_settings()
config = context.config
sync_url = settings.database_url.replace("+aiosqlite", "+pysqlite")
config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        dict(config.get_section(config.config_ini_section, {})),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
