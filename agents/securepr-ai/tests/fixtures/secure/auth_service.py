import os
import jwt
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

app = FastAPI()

# Restrict CORS to trusted domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://dashboard.example.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type"],
)

JWT_PUBLIC_KEY = os.environ.get("JWT_PUBLIC_KEY")
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            JWT_PUBLIC_KEY,
            algorithms=["RS256"],
            options={"verify_signature": True, "verify_exp": True}
        )
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

# Secure state mutation with authorization check
@app.post("/users/{user_id}/profile")
def update_profile(user_id: str, payload: dict, current_user: dict = Depends(get_current_user)):
    # Verify user ownership (Object-level authorization)
    if current_user.get("sub") != user_id and not current_user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    db.users.filter(id=user_id).update(**payload)
    return {"status": "success"}
