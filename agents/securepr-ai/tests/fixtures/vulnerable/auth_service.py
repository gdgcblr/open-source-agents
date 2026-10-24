import jwt
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Permissive CORS with credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Vulnerability 1: Hardcoded Secret
API_SECRET_KEY = "AKIA1234567890ABCDEF"

# Vulnerability 2: Unsafe JWT verification (verify=False)
def authenticate_token(token: str):
    # Decode token without signature verification
    payload = jwt.decode(token, verify=False, algorithms=["none"])
    return payload

# Vulnerability 3: State mutation endpoint missing authorization dependency (BOLA)
@app.post("/users/{user_id}/profile")
def update_profile(user_id: str, payload: dict):
    # Missing authentication dependency, direct update
    db.users.filter(id=user_id).update(**payload)
    return {"status": "success"}
