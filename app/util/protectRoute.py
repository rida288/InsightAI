from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.security.authHandler import AuthHandler
from app.service.userService import UserService
from app.core.database import get_db
from app.db.schema.user import UserOutput
from app.db.repository.tokenRepo import TokenRepository

security = HTTPBearer()

def get_current_user(
    session:Session=Depends(get_db), 
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> UserOutput:
    auth_exception = HTTPException(
        status_code = status.HTTP_401_UNAUTHORIZED, 
        detail = "Invalid authentication credentials"
    )
    
    token = credentials.credentials
    if TokenRepository(session=session).is_token_blacklisted(token=token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked/logged out"
        )
    
    payload = AuthHandler.decode_jwt(token=token)
    
    if payload and payload["user_id"]:
        try: 
            user = UserService(session=session).get_user_by_id(payload["user_id"])
            if not user.is_approved:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is suspended or pending admin approval"
                )
            return UserOutput(
                id = user.id,
                first_name = user.first_name,
                last_name = user.last_name,
                email = user.email,
                role = user.role,
                is_approved = user.is_approved
            )
        except Exception as e:
            raise e
    raise auth_exception

def get_current_admin(current_user: UserOutput = Depends(get_current_user)) -> UserOutput:
    if current_user.role != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user
