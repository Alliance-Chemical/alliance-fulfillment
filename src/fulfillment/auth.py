from itsdangerous import URLSafeTimedSerializer
from fastapi import Request, Response
from fulfillment.db import FulfillmentDB


def make_serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key)


def set_auth_cookie(
    response: Response, serializer: URLSafeTimedSerializer, role: str
) -> Response:
    token = serializer.dumps({"role": role})
    response.set_cookie(f"{role}_auth", token, httponly=True, max_age=86400)  # 24h
    return response


def check_auth(
    request: Request, serializer: URLSafeTimedSerializer, role: str
) -> bool:
    cookie = request.cookies.get(f"{role}_auth")
    if not cookie:
        return False
    try:
        data = serializer.loads(cookie, max_age=86400)
        return data.get("role") == role
    except Exception:
        return False


def require_password_set(db: FulfillmentDB, role: str) -> bool:
    """Returns True if a password has been configured for this role."""
    pwd = db.get_setting(f"{role}_password", "")
    return pwd != ""
