from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import fastapi_get_db
from app.infrastructure.repositories.UserRepository import UserRepository
from app.infrastructure.core import settings

from app.models.dtoModels.TokenDTO import TokenDTO
from app.models.dtoModels.RefreshTokenDTO import RefreshTokenDTO
from app.models.dtoModels.UserDTO import UserOutDTO

SECRET_KEY = settings.SECRET_KEY
ALGORITHM  = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_MINUTES = getattr(settings, "REFRESH_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7)

pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token/get-token")


class AuthService:

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        return pwd_context.verify(plain, hashed)

    @staticmethod
    def get_password_hash(password: str) -> str:
        return pwd_context.hash(password)

    async def authenticate_user(
        self,
        email: str,
        password: str,
        session: AsyncSession,
    ):
        repo = UserRepository(session)
        user = await repo.find_by_email(email)
        if user and self.verify_password(password, user.hashed_password):
            return user
        return None

    def create_access_token(self, data: dict, expires: timedelta | None = None) -> str:
        to_encode = data.copy()
        expire    = datetime.now(timezone.utc) + (expires or timedelta(minutes=15))
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    def create_refresh_token(self, data: dict, expires: timedelta | None = None) -> str:
        to_encode = data.copy()
        expire    = datetime.now(timezone.utc) + (
            expires or timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
        )
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    async def login_for_access_token(
        self,
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
        session:    AsyncSession,
    ) -> TokenDTO:
        """Проверяем email+password и выдаём JWT."""
        user = await self.authenticate_user(form_data.username, form_data.password, session)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token = self.create_access_token(
            data={"sub": user.email},
            expires=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        refresh_token = self.create_refresh_token({"sub": user.email})
        return TokenDTO(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )

    async def refresh_access_token(self, dto: RefreshTokenDTO) -> TokenDTO:
        refresh_token = dto.refresh_token
        creds_exc = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

        try:
            payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
            email: str | None = payload.get("sub")
            if email is None:
                raise creds_exc
        except InvalidTokenError:
            raise creds_exc

        access_token = self.create_access_token(
            data={"sub": email},
            expires=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        new_refresh_token = self.create_refresh_token({"sub": email})

        return TokenDTO(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
        )


async def get_current_user_service(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: AsyncSession = Depends(fastapi_get_db),
) -> UserOutDTO:
    creds_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str | None = payload.get("sub")
        if email is None:
            raise creds_exc
    except InvalidTokenError:
        raise creds_exc

    repo = UserRepository(session)
    user = await repo.find_by_email(email)
    if not user:
        raise creds_exc

    return UserOutDTO(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        role=user.role,
    )
