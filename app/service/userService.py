from app.db.repository.userRepo import UserRepository
from app.db.schema.user import UserInCreate, UserInLogin, UserOutput, UserWithToken, UserAdminCreate
from app.core.security.hashHelper import HashHelper
from app.core.security.authHandler import AuthHandler
from sqlalchemy.orm import Session
from fastapi import HTTPException

class UserService:
    def __init__(self, session:Session):
        self.__userRepository = UserRepository(session=session)
        
    def signup(self, user_details: UserInCreate) -> UserOutput:
        if self.__userRepository.user_exists_by_email(email=user_details.email):
            raise HTTPException(status_code=400, detail="User with this email already exists")
        
        hashed_password = HashHelper.get_password_hash(plain_password=user_details.password)
        user_details.password = hashed_password

        # If this is the first user in the system, automatically make them an approved Admin
        existing_users = self.__userRepository.get_all_users()
        if not existing_users:
            from app.db.models.user import User
            user = User(
                first_name=user_details.first_name,
                last_name=user_details.last_name,
                email=user_details.email,
                password=user_details.password,
                role="Admin",
                is_approved=True
            )
            self.__userRepository.session.add(user)
            self.__userRepository.session.commit()
            self.__userRepository.session.refresh(user)
            return user

        return self.__userRepository.create_user(user_data=user_details)
    
    def login(self, login_details:UserInLogin) -> UserWithToken:
        user = self.__userRepository.get_user_by_email(email=login_details.email)

        # Same message whether the email is unknown or the password is wrong, so the
        # login form can't be used to discover which emails have accounts. The
        # password is checked before approval status for the same reason.
        if not user or not HashHelper.verify_password(plain_password=login_details.password, hashed_password=user.password):
            raise HTTPException(status_code=400, detail="Invalid email or password")

        if not user.is_approved:
            raise HTTPException(status_code=403, detail="Account pending admin approval")

        token = AuthHandler.sign_jwt(user_id=user.id, role=user.role)
        if token:
            return UserWithToken(token=token)
        raise HTTPException(status_code=500, detail="Error generating token")
    
    def get_user_by_id(self, user_id:int):
        user = self.__userRepository.get_user_by_id(user_id=user_id)
        if not user:
            raise HTTPException(status_code=400, detail="User not found")
        return user
        
    def get_all_users(self):
        return self.__userRepository.get_all_users()
        
    def get_pending_users(self):
        return self.__userRepository.get_pending_users()
        
    def approve_user(self, user_id: int):
        user = self.__userRepository.approve_user(user_id=user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
        
    def _guard_admin_lockout(self, user_id: int, acting_admin_id: int, action: str):
        """
        Stops an admin from suspending/deleting themselves. This also guarantees at
        least one approved admin always remains: the one performing the action.
        """
        if user_id == acting_admin_id:
            raise HTTPException(status_code=400, detail=f"You cannot {action} your own account")

    def suspend_user(self, user_id: int, acting_admin_id: int):
        self._guard_admin_lockout(user_id, acting_admin_id, action="suspend")
        user = self.__userRepository.suspend_user(user_id=user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    def admin_create_user(self, user_details: UserAdminCreate) -> UserOutput:
        if self.__userRepository.user_exists_by_email(email=user_details.email):
            raise HTTPException(status_code=400, detail="User with this email already exists")
        hashed_password = HashHelper.get_password_hash(plain_password=user_details.password)
        user_details.password = hashed_password
        # Directly create the user with is_approved=True via model kwargs
        from app.db.models.user import User
        user = User(
            first_name=user_details.first_name,
            last_name=user_details.last_name,
            email=user_details.email,
            password=user_details.password,
            role=user_details.role,
            is_approved=True
        )
        self.__userRepository.session.add(user)
        self.__userRepository.session.commit()
        self.__userRepository.session.refresh(user)
        return user

    def update_user(self, user_id: int, data):
        if data.email is not None:
            existing = self.__userRepository.get_user_by_email(email=data.email)
            if existing and existing.id != user_id:
                raise HTTPException(status_code=400, detail="User with this email already exists")
        if data.password:
            data.password = HashHelper.get_password_hash(plain_password=data.password)
        user = self.__userRepository.update_user(user_id=user_id, data=data)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    def delete_user(self, user_id: int, acting_admin_id: int):
        from app.db.repository.projectRepo import ProjectRepository
        from app.service.projectService import ProjectService
        from app.core.service_cache import invalidate_chat_service

        self._guard_admin_lockout(user_id, acting_admin_id, action="delete")
        if not self.__userRepository.get_user_by_id(user_id=user_id):
            raise HTTPException(status_code=404, detail="User not found")

        # Delete the user's projects first so their files are removed from B2 and
        # their cached chat services are evicted (the DB cascade alone does neither).
        session = self.__userRepository.session
        project_service = ProjectService(session=session)
        for project in ProjectRepository(session=session).get_projects_by_owner(user_id):
            project_service.delete_project(project_id=project.id, current_user_id=user_id, is_admin=True)
            invalidate_chat_service(project.id)

        self.__userRepository.delete_user(user_id=user_id)
        return {"message": "User deleted successfully"}
