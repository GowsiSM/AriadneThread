import os

os.environ["DATABASE_PATH"] = "/nonexistent/readonly/path/db.sqlite"

import importlib


def test_db_falls_back_to_in_memory_on_bad_path():
    from app import db as db_module
    importlib.reload(db_module)
    # engine should be created without raising, using the in-memory fallback
    with db_module.engine.connect() as conn:
        pass
    db_module.log_audit("test_event", {"ok": True})
    session = db_module.get_session()
    rows = session.query(db_module.AuditLog).filter_by(event_type="test_event").all()
    session.close()
    assert len(rows) == 1
