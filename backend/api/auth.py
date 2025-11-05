from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
import httpx
import os
from datetime import datetime, timedelta
from jose import jwt, JWTError
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()

# Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI_DEV", "http://localhost:3060/auth/callback")
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-this-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Request/Response Models
class GoogleTokenRequest(BaseModel):
    code: str

class UserInfo(BaseModel):
    id: str
    email: str
    name: str
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    picture: Optional[str] = None
    email_verified: bool = False

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo

# Google OAuth Endpoints
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


@router.post("/google", response_model=AuthResponse)
async def google_auth(token_request: GoogleTokenRequest):
    """
    Exchange Google authorization code for access token and user info
    
    Flow:
    1. Receive authorization code from frontend
    2. Exchange code for access token with Google
    3. Fetch user information from Google
    4. Create/update user in database (TODO: implement database)
    5. Generate JWT token for our application
    6. Return JWT and user info to frontend
    """
    # Print received data from frontend
    print("\n" + "="*50)
    print("📥 RECEIVED DATA FROM FRONTEND:")
    print("="*50)
    print(f"Authorization Code: {token_request.code[:20]}..." if len(token_request.code) > 20 else f"Authorization Code: {token_request.code}")
    print("="*50 + "\n")
    
    try:
        # Step 1: Exchange authorization code for access token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": token_request.code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            
            if token_response.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to exchange code: {token_response.text}"
                )
            
            token_data = token_response.json()
            access_token = token_data.get("access_token")
            
            # Step 2: Fetch user information from Google
            userinfo_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if userinfo_response.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail="Failed to fetch user info from Google"
                )
            
            google_user = userinfo_response.json()
            
            # Print user data received from Google
            print("📊 USER DATA FROM GOOGLE:")
            print("="*50)
            print(f"Google User ID: {google_user.get('id')}")
            print(f"Email: {google_user.get('email')}")
            print(f"Name: {google_user.get('name')}")
            print(f"Given Name: {google_user.get('given_name')}")
            print(f"Family Name: {google_user.get('family_name')}")
            print(f"Picture URL: {google_user.get('picture')}")
            print(f"Email Verified: {google_user.get('verified_email')}")
            print("="*50 + "\n")
            
        # Step 3: Create user info object
        user_info = UserInfo(
            id=google_user["id"],
            email=google_user["email"],
            name=google_user.get("name", ""),
            given_name=google_user.get("given_name"),
            family_name=google_user.get("family_name"),
            picture=google_user.get("picture"),
            email_verified=google_user.get("verified_email", False)
        )
        
        # Step 4: Create or update user in your database
        # TODO: Implement your database logic here
        # Example:
        # user = await create_or_update_user(user_info)
        # For now, we'll just use the Google user data
        
        # Step 5: Generate JWT token for our application
        jwt_payload = {
            "sub": user_info.id,  # Subject (user ID)
            "email": user_info.email,
            "name": user_info.name,
            "picture": user_info.picture,
            "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
        }
        
        jwt_token = jwt.encode(jwt_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        # Print response being sent back to frontend
        print("📤 SENDING RESPONSE TO FRONTEND:")
        print("="*50)
        print(f"JWT Token: {jwt_token[:30]}...{jwt_token[-20:] if len(jwt_token) > 50 else jwt_token[30:]}")
        print(f"User ID: {user_info.id}")
        print(f"User Email: {user_info.email}")
        print(f"User Name: {user_info.name}")
        print("="*50 + "\n")
        
        return AuthResponse(
            access_token=jwt_token,
            user=user_info
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


@router.get("/me", response_model=UserInfo)
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Get current authenticated user from JWT token
    
    This endpoint validates the JWT token and returns the user information.
    Frontend should call this on app load to check if user is authenticated.
    """
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        # Check if token is expired
        exp = payload.get("exp")
        if exp and datetime.utcnow().timestamp() > exp:
            raise HTTPException(status_code=401, detail="Token has expired")
        
        user_info = UserInfo(
            id=payload["sub"],
            email=payload["email"],
            name=payload["name"],
            picture=payload.get("picture"),
            email_verified=True
        )
        
        return user_info
        
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid authentication token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")


@router.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Logout endpoint
    
    Note: With JWT tokens, logout is primarily handled on the client side
    by removing the token from storage. This endpoint can be used for:
    - Logging the logout event
    - Invalidating refresh tokens (if implemented)
    - Adding token to blacklist (if implemented)
    """
    # TODO: Implement token blacklist if needed
    return {"message": "Logged out successfully"}


@router.get("/config")
async def get_auth_config():
    """
    Get public OAuth configuration for frontend
    
    This allows the frontend to dynamically fetch OAuth configuration
    without hardcoding sensitive values.
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    
    return {
        "google_client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "scopes": ["openid", "email", "profile"]
    }

