import httpx
from fastapi import HTTPException
from jose import jwk, jwt
from jose.exceptions import JWTError

from app.config.settings import get_settings
from app.schema.auth import AuthResponse, TokenData


# Token validation function
async def validate_token(token: str) -> AuthResponse:
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

        # Extract username
        username = payload.get("preferred_username")
        if not username:
            return AuthResponse(
                status_code=401, detail="Token missing 'preferred_username'"
            )

        # Extract realm roles
        realm_roles = payload.get("realm_access", {}).get("roles", [])

        # Extract all client roles dynamically
        client_roles = []
        resource_access = payload.get("resource_access", {})
        for _, access in resource_access.items():
            roles = access.get("roles", [])
            client_roles.extend(roles)

        # Combine realm and client roles
        # Remove any duplicate roles if exists
        all_roles = list(set(realm_roles + client_roles))

        if not all_roles:
            return AuthResponse(status_code=401, detail="Token has no roles")

        return AuthResponse(
            status_code=200, detail=TokenData(username=username, roles=all_roles)
        )

    except JWTError as e:
        return AuthResponse(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        return AuthResponse(status_code=500, detail=f"Server error: {str(e)}")
