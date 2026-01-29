"""Auth routes for social login (starting with Kakao)."""

import logging
from datetime import timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.auth import create_access_token, get_current_user
from app.core.db import get_db
from app.core.models import User, UserIdentity


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class KakaoAuthRequest(BaseModel):
    """Request body for Kakao auth exchange."""

    code: str
    redirectUri: Optional[str] = None


class AuthUserResponse(BaseModel):
    """Basic user info returned after login."""

    id: str
    email: Optional[str] = None
    nickname: Optional[str] = None
    profileImage: Optional[str] = None


class AuthResponse(BaseModel):
    """Response after social login."""

    accessToken: str
    user: AuthUserResponse


def _get_or_create_user_from_kakao(
    kakao_id: str,
    email: Optional[str],
    nickname: Optional[str],
    profile_image_url: Optional[str],
    db: Session,
) -> User:
    """Upsert user and user identity based on Kakao profile."""
    identity = (
        db.query(UserIdentity)
        .filter(
            UserIdentity.provider == "kakao",
            UserIdentity.provider_user_id == kakao_id,
        )
        .first()
    )

    if identity:
        user = identity.user
        if nickname:
            user.nickname = nickname
        if profile_image_url:
            user.profile_image = profile_image_url
        user.last_login_at = user.last_login_at or None
        identity.provider_email = email or identity.provider_email
        identity.profile_nickname = nickname or identity.profile_nickname
        identity.profile_image_url = profile_image_url or identity.profile_image_url
        db.commit()
        db.refresh(user)
        return user

    user = User(
        email=email,
        nickname=nickname,
        profile_image=profile_image_url,
    )
    db.add(user)
    db.flush()

    identity = UserIdentity(
        user_id=user.id,
        provider="kakao",
        provider_user_id=kakao_id,
        provider_email=email,
        profile_nickname=nickname,
        profile_image_url=profile_image_url,
    )
    db.add(identity)
    db.commit()
    db.refresh(user)
    return user


@router.post("/kakao", response_model=AuthResponse)
async def kakao_login(payload: KakaoAuthRequest, db: Session = Depends(get_db)):
    """Exchange Kakao auth code for tokens, upsert user, and return JWT."""
    if not settings.KAKAO_REST_API_KEY or not settings.KAKAO_REDIRECT_URI:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kakao OAuth is not configured",
        )

    redirect_uri = payload.redirectUri or settings.KAKAO_REDIRECT_URI

    # 1) Get access token from Kakao
    token_url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.KAKAO_REST_API_KEY,
        "redirect_uri": redirect_uri,
        "code": payload.code,
    }
    if settings.KAKAO_CLIENT_SECRET:
        data["client_secret"] = settings.KAKAO_CLIENT_SECRET

    async with httpx.AsyncClient() as client:
        token_res = await client.post(token_url, data=data)

    if token_res.status_code != 200:
        logger.error("Kakao token error: %s", token_res.text)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to obtain Kakao access token",
        )

    token_json = token_res.json()
    access_token = token_json.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Kakao token response",
        )

    # 2) Fetch user info
    me_url = "https://kapi.kakao.com/v2/user/me"
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        me_res = await client.get(me_url, headers=headers)

    if me_res.status_code != 200:
        logger.error("Kakao userinfo error: %s", me_res.text)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to fetch Kakao user info",
        )

    me = me_res.json()
    kakao_id = str(me.get("id"))
    kakao_account = me.get("kakao_account", {}) or {}
    profile = kakao_account.get("profile", {}) or {}

    email = kakao_account.get("email")
    nickname = profile.get("nickname")
    profile_image_url = profile.get("profile_image_url") or profile.get("thumbnail_image_url")

    user = _get_or_create_user_from_kakao(
        kakao_id=kakao_id,
        email=email,
        nickname=nickname,
        profile_image_url=profile_image_url,
        db=db,
    )

    jwt_expires = timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    token = create_access_token(
        {
            "sub": user.id,
            "provider": "kakao",
        },
        expires_delta=jwt_expires,
    )

    return AuthResponse(
        accessToken=token,
        user=AuthUserResponse(
            id=user.id,
            email=user.email,
            nickname=user.nickname,
            profileImage=user.profile_image,
        ),
    )


@router.get("/me", response_model=AuthUserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Return the current authenticated user."""
    return AuthUserResponse(
        id=current_user.id,
        email=current_user.email,
        nickname=current_user.nickname,
        profileImage=current_user.profile_image,
    )

