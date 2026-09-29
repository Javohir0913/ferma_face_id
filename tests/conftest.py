import os
import sys
import tempfile
from pathlib import Path

# Testlar hech qachon haqiqiy bazaga yoki Telegramga tegmasligi uchun —
# modullar import qilinishidan OLDIN muhit o'zgaruvchilari o'rnatiladi.
_TMP = Path(tempfile.mkdtemp(prefix="ferma_test_"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_TMP / 'test.db').as_posix()}"
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
