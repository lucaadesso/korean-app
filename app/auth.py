"""
auth.py – Google OAuth2 via Authlib + session cookie management.

Flow:
  1. /auth/login      → redirect to Google
  2. /auth/callback   → exchange code → get user info → upsert DB → set session
  3. /auth/logout     → clear session
"""
import os
from typing import Optional

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.config import Config

from app.database import get_db
from app.models import User

# ─── OAuth setup ─────────────────────────────────────────────────────────────

config = Config(environ=os.environ)

oauth = OAuth(config)
oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
    client_kwargs={"scope": "openid email profile"},
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ─── Session helpers ──────────────────────────────────────────────────────────

SESSION_KEY = "user_id"


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Return the authenticated User from session, or None."""
    user_id = request.session.get(SESSION_KEY)
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Like get_current_user but redirects to /login if not authenticated."""
    user = get_current_user(request, db)
    if user is None:
        raise _LoginRequired()
    return user


class _LoginRequired(Exception):
    pass


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("/login")
async def login(request: Request):
    redirect_uri = str(request.url_for("auth_callback"))
    # In development allow http
    if redirect_uri.startswith("http://") and os.getenv("ENVIRONMENT") == "production":
        redirect_uri = redirect_uri.replace("http://", "https://", 1)
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="auth_callback")
async def callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as e:
        return RedirectResponse(url=f"/?error={e.error}")

    userinfo = token.get("userinfo") or await oauth.google.userinfo(token=token)

    google_id = userinfo["sub"]
    email = userinfo["email"]
    name = userinfo.get("name", email)
    picture = userinfo.get("picture")

    user = db.query(User).filter(User.google_id == google_id).first()
    if not user:
        user = User(google_id=google_id, email=email, name=name, picture=picture)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.name = name
        user.picture = picture
        db.commit()

    request.session[SESSION_KEY] = user.id
    return RedirectResponse(url="/dashboard")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")
