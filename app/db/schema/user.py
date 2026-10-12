from pydantic import EmailStr, BaseModel
from typing import Union, Literal

#what we expect in signup
class UserInCreate(BaseModel):
    first_name: str
    last_name: str 
    email: EmailStr 
    password: str

# For admin-created users — auto-approved, with optional role
class UserAdminCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    role: Literal["User", "Admin"] = "User"
    
class UserOutput(BaseModel):
    id: int 
    first_name: str
    last_name: str 
    email: EmailStr
    role: str
    is_approved: bool
    
class UserInUpdate(BaseModel):
    id: int 
    first_name: Union[str, None] = None 
    last_name: Union[str, None] = None 
    email: Union[EmailStr, None] = None 
    password: Union[str, None] = None  
    
class UserInLogin(BaseModel):
    email: EmailStr 
    password: str
    
class UserWithToken(BaseModel):
    token: str 