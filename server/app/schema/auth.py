from typing import List

from pydantic import BaseModel


# Auth models
class TokenData(BaseModel):
    username: str
    roles: List[str]
