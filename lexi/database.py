"""Small SQLAlchemy database layer: SQLite locally, PostgreSQL on Render."""
from pathlib import Path
import os
import secrets
import tempfile
import time

from flask import g
from sqlalchemy import Integer, String, Text, LargeBinary, JSON, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(30))
    username_key: Mapped[str] = mapped_column(String(30), unique=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))
    avatar: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    avatar_version: Mapped[int] = mapped_column(Integer, default=0)
    preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)


class RateBucket(Base):
    __tablename__ = 'auth_rate_buckets'
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)


def local_secret(instance):
    """Create a private key once; independent workers read the same complete file."""
    directory = Path(instance)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / '.session-key'
    if not path.exists():
        with tempfile.NamedTemporaryFile(dir=directory, prefix='.key-', delete=False) as temporary:
            temporary.write(secrets.token_hex(32).encode('ascii'))
            temporary_path = Path(temporary.name)
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            pass
        finally:
            temporary_path.unlink(missing_ok=True)
    value = path.read_text(encoding='ascii').strip()
    if len(value) < 32:
        raise RuntimeError('The local session key is invalid. Restore instance/.session-key or set SECRET_KEY.')
    return value


def init_database(app):
    url = app.config['DATABASE_URL']
    if url.startswith('postgres://'):
        url = 'postgresql+psycopg://' + url[len('postgres://'):]
    elif url.startswith('postgresql://'):
        url = 'postgresql+psycopg://' + url[len('postgresql://'):]
    options = {'pool_pre_ping': True, 'hide_parameters': True}
    if url.startswith('sqlite:'):
        options['connect_args'] = {'check_same_thread': False, 'timeout': 15}
        if ':memory:' in url:
            options['poolclass'] = StaticPool
    engine = create_engine(url, **options)
    if engine.dialect.name not in ('sqlite', 'postgresql'):
        raise RuntimeError('LEXI supports SQLite or PostgreSQL for account data.')
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def sqlite_options(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')
    # Serialize schema creation when multiple Gunicorn workers start together.
    with engine.connect() as connection:
        if engine.dialect.name == 'sqlite':
            connection.exec_driver_sql('BEGIN IMMEDIATE')
        else:
            connection.exec_driver_sql('SELECT pg_advisory_xact_lock(20261021)')
        Base.metadata.create_all(connection)
        connection.commit()
    app.extensions['account_engine'] = engine
    app.extensions['account_sessions'] = sessionmaker(engine, expire_on_commit=False)

    @app.teardown_appcontext
    def close_session(error=None):
        database = g.pop('account_db', None)
        if database is not None:
            database.close()

    return engine


def get_db():
    from flask import current_app
    if 'account_db' not in g:
        g.account_db = current_app.extensions['account_sessions']()
    return g.account_db
