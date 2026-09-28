import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from loguru import logger

from app.config import settings

basic = HTTPBasic(auto_error=False)


def require_auth(request: Request, creds: HTTPBasicCredentials | None = Depends(basic)):
    password = settings.auth.app_password
    if not password:
        return
    if creds and secrets.compare_digest(creds.password.encode(), password.encode()):
        return
    logger.info("auth failed for {} {}", request.method, request.url.path)
    raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})
