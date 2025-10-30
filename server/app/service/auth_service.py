from urllib.parse import urlencode

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2AuthorizationCodeBearer
from jose import jwk, jwt
from jose.exceptions import JWTError

from app.config.settings import get_settings
from app.schema.auth import TokenData

# Initalizing the oauth schema
oauth2_schema = OAuth2AuthorizationCodeBearer(
    authorizationUrl=get_settings().AUTHORIZATION_URL,
    tokenUrl=get_settings().TOKEN_URL,
    auto_error=False,
)


# Token validation function
async def validate_token(token: str) -> TokenData:
    try:
        # Fetch JWKS
        async with httpx.AsyncClient() as client:
            response = await client.get(get_settings().JWKS_URL)
            response.raise_for_status()
            jwks = response.json()

        # Decode the token headers to get the key ID (kid)
        headers = jwt.get_unverified_headers(token)
        kid = headers.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="Token missing 'kid' header")

        # Find the correct key in the JWKS
        key_data = next((key for key in jwks["keys"] if key["kid"] == kid), None)
        if not key_data:
            raise HTTPException(
                status_code=401, detail="Matching key not found in JWKS"
            )

        # Convert JWK to RSA public key
        public_key = jwk.construct(key_data).public_key()

        # Verify the token
        payload = jwt.decode(
            token, key=public_key, algorithms=["RS256"], options={"verify_aud": False}
        )

        # Extract username and roles
        username = payload.get("preferred_username")
        roles = payload.get("realm_access", {}).get("roles", [])
        if not username or not roles:
            raise HTTPException(status_code=401, detail="Token missing required claims")

        return TokenData(username=username, roles=roles)

    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# Dependency to get the current user
async def get_current_user(token: str = Depends(oauth2_schema)):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await validate_token(token)


# Role-Based Access Control (RBAC)
def has_role(required_role: str):
    def role_checker(token_data: TokenData = Depends(get_current_user)) -> TokenData:
        if required_role not in token_data.roles:
            raise HTTPException(status_code=403, detail="Not authorized")
        return token_data

    return role_checker


async def get_auth_url():
    params = {
        "client_id": get_settings().KEYCLOAK_CLIENT_ID,
        "redirect_uri": get_settings().REDIRECT_URI,
        "response_type": "code",
        "scope": "openid",
    }
    return f"{get_settings().AUTHORIZATION_URL}?{urlencode(params)}"


async def get_access_token(code: str):
    async with httpx.AsyncClient() as client:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": get_settings().KEYCLOAK_CLIENT_ID,
            "client_secret": get_settings().KEYCLOAK_CLIENT_SECRET,
            "redirect_uri": get_settings().REDIRECT_URI,
        }
        resp = await client.post(get_settings().TOKEN_URL, data=data)
        token_data = resp.json()
        return token_data
