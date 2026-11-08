"""Delete the REACH database and reinitialize it (tables + seed sectors/units).

Usage (from backend/):  python scripts/reset_db.py
Stop the API server first; on Windows a running server keeps the SQLite file locked.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from sqlalchemy.engine import make_url  # noqa: E402

from database import DATABASE_URL, Base, SessionLocal, engine  # noqa: E402
from main import init_db  # noqa: E402


def main() -> int:
    url = make_url(DATABASE_URL)
    db_file = url.database if url.get_backend_name() == "sqlite" else None
    engine.dispose()
    if db_file and db_file != ":memory:":
        path = Path(db_file).resolve()  # relative to cwd, same as the engine
        if path.exists():
            try:
                path.unlink()
            except PermissionError:
                print(f"Could not delete {path}: is the server still running?")
                return 1
            print(f"Deleted {path}")
    else:
        Base.metadata.drop_all(bind=engine)
        print(f"Dropped all tables in {url.render_as_string(hide_password=True)}")
    with SessionLocal() as db:
        init_db(db)
    print("Reinitialized: tables created, sectors and units seeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
