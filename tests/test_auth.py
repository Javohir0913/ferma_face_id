import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from davomat import auth
from davomat.auth import AuthError, verify_login_widget, verify_webapp_init_data

TOKEN = "123456:TEST-TOKEN"


def _signed_init_data(user_id=42, auth_date=None, token=TOKEN):
    fields = {"auth_date": str(auth_date or int(time.time())), "query_id": "AAA",
              "user": json.dumps({"id": user_id, "first_name": "Ali"})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_webapp_valid():
    assert verify_webapp_init_data(_signed_init_data(), TOKEN)["id"] == 42


def test_webapp_wrong_token_rejected():
    with pytest.raises(AuthError):
        verify_webapp_init_data(_signed_init_data(token="999:OTHER"), TOKEN)


def test_webapp_tampered_user_rejected():
    data = _signed_init_data().replace("%22id%22%3A+42", "%22id%22%3A+1")
    with pytest.raises(AuthError):
        verify_webapp_init_data(data, TOKEN)


def test_webapp_expired_rejected():
    with pytest.raises(AuthError):
        verify_webapp_init_data(_signed_init_data(auth_date=int(time.time()) - 2 * 86400), TOKEN)


def test_login_widget_valid_and_tampered():
    d = {"id": "42", "first_name": "Ali", "auth_date": str(int(time.time()))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(d.items()))
    d["hash"] = hmac.new(hashlib.sha256(TOKEN.encode()).digest(), check.encode(), hashlib.sha256).hexdigest()
    assert verify_login_widget(dict(d), TOKEN)["id"] == 42
    d["id"] = "1"
    with pytest.raises(AuthError):
        verify_login_widget(d, TOKEN)


def test_session_token_roundtrip_and_tamper(monkeypatch):
    monkeypatch.setattr(auth, "SESSION_SECRET", "s3cret")
    t = auth.make_token(42, "Ali")
    assert auth.read_token(t)["uid"] == 42
    body, sig = t.rsplit(".", 1)
    with pytest.raises(AuthError):
        auth.read_token(body + "." + sig[:-2] + "AA")
    monkeypatch.setattr(auth, "SESSION_SECRET", "other")
    with pytest.raises(AuthError):
        auth.read_token(t)
