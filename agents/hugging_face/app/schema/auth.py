from typing import List, Union

from pydantic import BaseModel


# Auth models
class TokenData(BaseModel):
    username: str
    roles: List[str]


# Auth Response
class AuthResponse(BaseModel):
    status_code: int
    detail: Union[TokenData, str]
