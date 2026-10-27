"""Explicit, transactional account copy into an empty database."""
from pathlib import Path
import time

from sqlalchemy import func, inspect, select, text

from .database import Base, DataMigration, ISOLATION_MIGRATION, OAuthIdentity, User, account_engine


def database_identity(engine):
    url = engine.url
    if engine.dialect.name == 'sqlite':
        return ('sqlite', str(Path(url.database or ':memory:').resolve()))
    return (engine.dialect.name, url.host, url.port or 5432, url.database)


def copy_accounts(source_url, target_url, apply=False):
    source, target = account_engine(source_url), account_engine(target_url)
    try:
        if database_identity(source) == database_identity(target):
            raise ValueError('Source and destination must be different databases.')
        if source.dialect.name == 'sqlite' and not Path(source.url.database).is_file():
            raise ValueError('The source SQLite file does not exist.')
        source_tables = set(inspect(source).get_table_names())
        if 'users' not in source_tables:
            raise ValueError('The source has no LEXI accounts table.')
        target_exists = target.dialect.name != 'sqlite' or Path(target.url.database).is_file()
        target_tables = set(inspect(target).get_table_names()) if target_exists else set()
        if 'users' in target_tables:
            with target.connect() as connection:
                if connection.scalar(select(func.count()).select_from(User)):
                    raise ValueError('The destination already has users. No accounts were copied.')
        with source.connect() as connection:
            connection = connection.execution_options(isolation_level='REPEATABLE READ') if source.dialect.name == 'postgresql' else connection
            if source.dialect.name == 'sqlite':
                connection.exec_driver_sql('BEGIN')
            else:
                connection.begin()
                connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            counts = {'users': connection.scalar(select(func.count()).select_from(User)),
                      'identities': connection.scalar(select(func.count()).select_from(OAuthIdentity)) if 'oauth_identities' in source_tables else 0}
            if not apply:
                return counts
            users = [dict(row) for row in connection.execute(select(User.__table__)).mappings()]
            identities = [dict(row) for row in connection.execute(select(OAuthIdentity.__table__)).mappings()] if counts['identities'] else []
            migrations = [dict(row) for row in connection.execute(select(DataMigration.__table__)).mappings()] if 'data_migrations' in source_tables else []
            with target.connect() as destination:
                if target.dialect.name == 'sqlite':
                    destination.exec_driver_sql('BEGIN IMMEDIATE')
                else:
                    destination.exec_driver_sql('SELECT pg_advisory_xact_lock(20261021)')
                Base.metadata.create_all(destination)
                if destination.scalar(select(func.count()).select_from(User)) or destination.scalar(select(func.count()).select_from(OAuthIdentity)):
                    raise ValueError('The destination is not empty. No accounts were copied.')
                if users:
                    destination.execute(User.__table__.insert(), users)
                if identities:
                    destination.execute(OAuthIdentity.__table__.insert(), identities)
                existing = set(destination.scalars(select(DataMigration.key)))
                for row in migrations:
                    if row['key'] not in existing:
                        destination.execute(DataMigration.__table__.insert().values(**row))
                        existing.add(row['key'])
                # Never replay the historic progress-reset migration after a copy.
                if ISOLATION_MIGRATION not in existing:
                    destination.execute(DataMigration.__table__.insert().values(key=ISOLATION_MIGRATION, applied_at=int(time.time())))
                if target.dialect.name == 'postgresql':
                    for model, rows in ((User, users), (OAuthIdentity, identities)):
                        if rows:
                            destination.execute(text("SELECT setval(pg_get_serial_sequence(:table, 'id'), :value, true)"), {'table': model.__tablename__, 'value': max(row['id'] for row in rows)})
                destination.commit()
            return counts
    finally:
        source.dispose()
        target.dispose()
