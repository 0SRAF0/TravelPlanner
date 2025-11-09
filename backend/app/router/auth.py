from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
import httpx
from datetime import datetime, timedelta
from jose import jwt, JWTError
from app.db.database import get_users_collection
from app.models.user import User
from app.core.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    GOOGLE_TOKEN_URL,
    GOOGLE_USERINFO_URL,
    JWT_SECRET,
    JWT_ALGORITHM,
    JWT_EXPIRATION_HOURS,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()

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
        
        # Step 4: Create or update user in MongoDB using User model
        users_collection = get_users_collection()
        
        # Check if user already exists
        existing_user = await users_collection.find_one({"google_id": user_info.id})
        
        current_time = datetime.utcnow()
        
        if existing_user:
            # Update existing user using User model for validation
            user_doc = User(
                google_id=user_info.id,
                email=user_info.email,
                name=user_info.name,
                given_name=user_info.given_name,
                family_name=user_info.family_name,
                picture=user_info.picture,
                email_verified=user_info.email_verified,
                created_at=existing_user.get("created_at", current_time),
                updated_at=current_time,
                last_login=current_time
            )
            
            update_result = await users_collection.update_one(
                {"google_id": user_info.id},
                {"$set": user_doc.model_dump(exclude={"created_at"})}
            )
            print("💾 DATABASE OPERATION:")
            print("="*50)
            print(f"Operation: UPDATE")
            print(f"Modified Count: {update_result.modified_count}")
            print(f"Google ID: {user_info.id}")
            print(f"Email: {user_info.email}")
            print(f"Name: {user_info.name}")
            print("="*50 + "\n")
        else:
            # Create new user using User model
            user_doc = User(
                google_id=user_info.id,
                email=user_info.email,
                name=user_info.name,
                given_name=user_info.given_name,
                family_name=user_info.family_name,
                picture=user_info.picture,
                email_verified=user_info.email_verified,
                created_at=current_time,
                updated_at=current_time,
                last_login=current_time
            )
            
            insert_result = await users_collection.insert_one(user_doc.model_dump())
            print("💾 DATABASE OPERATION:")
            print("="*50)
            print(f"Operation: CREATE")
            print(f"Inserted ID: {insert_result.inserted_id}")
            print(f"Google ID: {user_info.id}")
            print(f"Email: {user_info.email}")
            print(f"Name: {user_info.name}")
            print("="*50 + "\n")
        
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
        raise HTTPException(status_code=500, detail="Google OAuth client ID not configured")
    if not GOOGLE_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="Google OAuth redirect URI not configured")
    
    return {
        "google_client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "scopes": ["openid", "email", "profile"]
    }

