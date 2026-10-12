from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.db.schema.user import UserOutput, UserAdminCreate, UserInUpdate
from app.service.userService import UserService
from app.util.protectRoute import get_current_admin

adminRouter = APIRouter()

@adminRouter.get("/users", response_model=List[UserOutput])
def get_all_users(
    session: Session = Depends(get_db),
    admin_user: UserOutput = Depends(get_current_admin)
):
    try:
        return UserService(session=session).get_all_users()
    except Exception as e:
        print(e)
        raise e

@adminRouter.get("/users/pending", response_model=List[UserOutput])
def get_pending_users(
    session: Session = Depends(get_db),
    admin_user: UserOutput = Depends(get_current_admin)
):
    try:
        return UserService(session=session).get_pending_users()
    except Exception as e:
        print(e)
        raise e

@adminRouter.post("/users", response_model=UserOutput, status_code=201)
def admin_create_user(
    user_data: UserAdminCreate,
    session: Session = Depends(get_db),
    admin_user: UserOutput = Depends(get_current_admin)
):
    try:
        return UserService(session=session).admin_create_user(user_details=user_data)
    except Exception as e:
        print(e)
        raise e

@adminRouter.put("/users/{user_id}", response_model=UserOutput)
def update_user(
    user_id: int,
    user_data: UserInUpdate,
    session: Session = Depends(get_db),
    admin_user: UserOutput = Depends(get_current_admin)
):
    try:
        return UserService(session=session).update_user(user_id=user_id, data=user_data)
    except Exception as e:
        print(e)
        raise e

@adminRouter.put("/users/{user_id}/approve", response_model=UserOutput)
def approve_user(
    user_id: int,
    session: Session = Depends(get_db),
    admin_user: UserOutput = Depends(get_current_admin)
):
    try:
        return UserService(session=session).approve_user(user_id=user_id)
    except Exception as e:
        print(e)
        raise e

@adminRouter.put("/users/{user_id}/suspend", response_model=UserOutput)
def suspend_user(
    user_id: int,
    session: Session = Depends(get_db),
    admin_user: UserOutput = Depends(get_current_admin)
):
    try:
        return UserService(session=session).suspend_user(user_id=user_id, acting_admin_id=admin_user.id)
    except Exception as e:
        print(e)
        raise e

@adminRouter.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    session: Session = Depends(get_db),
    admin_user: UserOutput = Depends(get_current_admin)
):
    try:
        return UserService(session=session).delete_user(user_id=user_id, acting_admin_id=admin_user.id)
    except Exception as e:
        print(e)
        raise e
