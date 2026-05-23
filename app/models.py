from pydantic import BaseModel, Field
from app.config import USERNAME_PATTERN, PIN_PATTERN


class RegisterRequest(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    pin: str = Field(pattern=PIN_PATTERN)
    display_name: str = Field(min_length=1, max_length=40)


class LoginRequest(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    pin: str = Field(pattern=PIN_PATTERN)


class AutoLoginRequest(BaseModel):
    token: str
