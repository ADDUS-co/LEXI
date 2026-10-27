"""Small SQLAlchemy database layer: SQLite locally, PostgreSQL on Render."""
from pathlib import Path
import os
import secrets
import tempfile
import time

from flask import g
from sqlalchemy import Integer, String, Text, LargeBinary, JSON, ForeignKey, UniqueConstraint, create_engine, event, select, update
from sqlalchemy.engine import make_url
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


class OAuthIdentity(Base):
    __tablename__ = 'oauth_identities'
    __table_args__ = (UniqueConstraint('provider', 'subject'), UniqueConstraint('user_id', 'provider'))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    provider: Mapped[str] = mapped_column(String(16))
    subject: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))


class OAuthState(Base):
    """Short-lived authorization metadata, never provider access/refresh tokens."""
    __tablename__ = 'oauth_states'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[str] = mapped_column(Text)
    binding: Mapped[str] = mapped_column(String(64), index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    intent: Mapped[str] = mapped_column(String(16))
    expires_at: Mapped[int] = mapped_column(Integer, index=True)


PROGRESS_VERSION = 2
ISOLATION_MIGRATION = 'account-progress-isolation-v2'


class DataMigration(Base):
    __tablename__ = 'data_migrations'
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    applied_at: Mapped[int] = mapped_column(Integer)


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


def account_engine(url):
    """Shared connection policy for the app and the explicit database-copy tool."""
    url = url.strip()
    if url.startswith('postgres://'):
        url = 'postgresql+psycopg://' + url[len('postgres://'):]
    elif url.startswith('postgresql://'):
        url = 'postgresql+psycopg://' + url[len('postgresql://'):]
    url = make_url(url)
    options = {'pool_pre_ping': True, 'hide_parameters': True}
    if url.get_backend_name() == 'sqlite':
        options['connect_args'] = {'check_same_thread': False, 'timeout': 15}
        if url.database == ':memory:':
            options['poolclass'] = StaticPool
    elif url.get_backend_name() == 'postgresql':
        options.update(connect_args={'connect_timeout': 10, 'prepare_threshold': None}, pool_recycle=300, pool_timeout=15)
        if (url.host or '').lower().endswith('.neon.tech'):
            if url.query.get('sslmode', 'require') not in ('require', 'verify-ca', 'verify-full'):
                raise RuntimeError('Neon connections require TLS: use sslmode=require or stronger.')
            if 'sslmode' not in url.query:
                url = url.update_query_dict({'sslmode': 'require'})
    engine = create_engine(url, **options)
    if engine.dialect.name not in ('sqlite', 'postgresql'):
        raise RuntimeError('LEXI supports SQLite or PostgreSQL for account data.')
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def sqlite_options(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')
    return engine


def init_database(app):
    engine = account_engine(app.config['DATABASE_URL'])
    # Serialize schema creation when multiple Gunicorn workers start together.
    with engine.connect() as connection:
        if engine.dialect.name == 'sqlite':
            connection.exec_driver_sql('BEGIN IMMEDIATE')
        else:
            connection.exec_driver_sql('SELECT pg_advisory_xact_lock(20261021)')
        Base.metadata.create_all(connection)
        if connection.scalar(select(DataMigration.key).where(DataMigration.key == ISOLATION_MIGRATION)) is None:
            # Requested one-time clean start for all existing learning profiles.
            # Credentials and photos stay intact. The marker makes restarts safe.
            connection.execute(update(User).values(preferences=None, revision=User.revision + 1))
            connection.execute(DataMigration.__table__.insert().values(key=ISOLATION_MIGRATION, applied_at=int(time.time())))
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
