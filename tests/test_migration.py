"""Database copies preserve account data and never overwrite a populated target."""
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import func, select
from werkzeug.security import generate_password_hash

from app import create_app
from lexi.database import DataMigration, ISOLATION_MIGRATION, OAuthIdentity, User, account_engine, get_db
from lexi.migration import copy_accounts


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source = 'sqlite:///'+str(Path(self.tmp.name)/'source.sqlite3')
        self.target_file = Path(self.tmp.name)/'target.sqlite3'
        self.target = 'sqlite:///'+str(self.target_file)
        self.app = create_app({'TESTING': True, 'DATABASE_URL': self.source})
        with self.app.app_context():
            self.hash = generate_password_hash('Copy-test-password-42', method='scrypt')
            user = User(username='Copy_user', username_key='copy_user', email='copy@example.com', password_hash=self.hash,
                        avatar=b'test-avatar-bytes', avatar_version=2, preferences={'saved': ['law-equity'], 'history': [{'id': 'law-equity', 'date': '2026-10-27'}], 'theme': 'studio'}, revision=9)
            get_db().add(user);get_db().flush()
            get_db().add(OAuthIdentity(user_id=user.id, provider='google', subject='stable-test-subject'))
            get_db().commit()

    def tearDown(self):
        self.app.extensions['account_engine'].dispose()
        self.tmp.cleanup()

    def test_preview_does_not_create_a_destination_file(self):
        self.assertEqual(copy_accounts(self.source, self.target), {'users': 1, 'identities': 1})
        self.assertFalse(self.target_file.exists())

    def test_copy_preserves_password_photo_progress_identity_and_restart(self):
        self.assertEqual(copy_accounts(self.source, self.target, apply=True), {'users': 1, 'identities': 1})
        for _ in range(2):
            target = create_app({'TESTING': True, 'DATABASE_URL': self.target})
            with target.app_context():
                user = get_db().scalar(select(User))
                self.assertEqual(user.password_hash, self.hash)
                self.assertEqual(user.avatar, b'test-avatar-bytes')
                self.assertEqual(user.preferences['saved'], ['law-equity'])
                self.assertEqual(user.revision, 9)
                self.assertEqual(get_db().scalar(select(OAuthIdentity)).user_id, user.id)
                self.assertEqual(get_db().scalar(select(func.count()).select_from(DataMigration).where(DataMigration.key == ISOLATION_MIGRATION)), 1)
            target.extensions['account_engine'].dispose()

    def test_existing_destination_is_never_overwritten(self):
        copy_accounts(self.source, self.target, apply=True)
        for apply in (False, True):
            with self.assertRaisesRegex(ValueError, 'already has users'):
                copy_accounts(self.source, self.target, apply=apply)
        with self.app.app_context():
            self.assertEqual(get_db().scalar(select(User)).revision, 9)

    def test_same_database_and_missing_source_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'different'):
            copy_accounts(self.source, self.source, apply=True)
        with self.assertRaisesRegex(ValueError, 'does not exist'):
            copy_accounts('sqlite:///'+str(Path(self.tmp.name)/'missing.sqlite3'), self.target)
        self.assertFalse(self.target_file.exists())

    def test_neon_urls_use_psycopg_and_require_tls(self):
        for prefix in ('postgres://', 'postgresql://', 'postgresql+psycopg://'):
            engine = account_engine(prefix+'test:password@ep-example.neon.tech/neondb')
            self.assertEqual(engine.url.drivername, 'postgresql+psycopg')
            self.assertEqual(engine.url.query['sslmode'], 'require')
            self.assertTrue(engine.hide_parameters)
            engine.dispose()
        with self.assertRaisesRegex(RuntimeError, 'TLS'):
            account_engine('postgresql://test:password@ep-example.neon.tech/neondb?sslmode=disable')


if __name__ == '__main__':
    unittest.main()
