import os
import sys
import tempfile
from pathlib import Path

# Чтобы тесты никогда не трогали настоящую базу или Telegram —
# переменные окружения задаются ДО импорта модулей.
_TMP = Path(tempfile.mkdtemp(prefix="ferma_test_"))
# Если задан TEST_DATABASE_URL=postgresql+asyncpg://.../ferma_test — тесты идут на PostgreSQL
# (база каждый раз очищается, поэтому в имени обязательно должно быть «test»).
_PG = os.environ.get("TEST_DATABASE_URL", "")
os.environ["DATABASE_URL"] = _PG or f"sqlite+aiosqlite:///{(_TMP / 'test.db').as_posix()}"
if _PG:
    import sqlalchemy
    assert "test" in _PG.rsplit("/", 1)[1], "Testlar faqat nomida 'test' bo'lgan bazada yuradi"
    _eng = sqlalchemy.create_engine("postgresql+psycopg://" + _PG.split("://", 1)[1])
    with _eng.begin() as _c:
        _c.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    _eng.dispose()
os.environ["TG_TOKEN"] = ""
os.environ["TG_CHATS"] = "-100500"
os.environ["SESSION_SECRET"] = "test-secret"
os.environ["DEV_LOGIN"] = "0"
os.environ["ADMIN_TELEGRAM_IDS"] = ""
os.environ["SUPERADMIN_TELEGRAM_ID"] = "900"
os.environ["PUBLIC_BASE_URL"] = "https://example.test"
os.environ["CHECKIN_PHOTO_DIR"] = str(_TMP / "checkins")
os.environ["COOKIE_SECURE"] = "0"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
