"""Copy LEXI accounts. Connection strings are read only from environment variables."""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy.exc import SQLAlchemyError
from lexi.migration import copy_accounts


def main():
    parser = argparse.ArgumentParser(description='Preview an account copy into an empty Neon/PostgreSQL database.')
    parser.add_argument('--apply', action='store_true', help='Copy after checking the source and empty destination; default is read-only.')
    args = parser.parse_args()
    source, target = os.environ.get('LEXI_SOURCE_DATABASE_URL'), os.environ.get('DATABASE_URL')
    if not source or not target:
        parser.error('Set LEXI_SOURCE_DATABASE_URL and DATABASE_URL in the environment. Do not pass secrets as command-line arguments.')
    try:
        counts = copy_accounts(source, target, apply=args.apply)
    except ValueError as error:
        parser.exit(1, str(error)+'\n')
    except SQLAlchemyError:
        parser.exit(1, 'Could not connect or copy. Check database permissions, connection strings and TLS. Source data was not changed.\n')
    action = 'Copied' if args.apply else 'Read-only preview'
    print(f"{action}: {counts['users']} users, {counts['identities']} connected identities.")
    if not args.apply:
        print('No data was changed. Review the source and destination, then use --apply to copy into an empty destination.')


if __name__ == '__main__':
    main()
