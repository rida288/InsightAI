from .base import BaseRepository
from app.db.models.user import User 
from app.db.schema.user import UserInCreate

class UserRepository(BaseRepository):
    def create_user(self, user_data:UserInCreate):
        newUser = User(**user_data.model_dump(exclude_none=True))
        
        self.session.add(instance=newUser)
        self.session.commit()
        self.session.refresh(instance=newUser)
        
        return newUser
    
    def user_exists_by_email(self, email:str)->bool:
        user = self.session.query(User).filter_by(email=email).first()
        return bool(user)
    
    def get_user_by_email(self, email:str)->User:
            user = self.session.query(User).filter_by(email=email).first()
            return user
        
    def get_user_by_id(self, user_id:int)->User:
        user = self.session.query(User).filter_by(id=user_id).first()
        return user
        
    def get_all_users(self):
        return self.session.query(User).all()
        
    def get_pending_users(self):
        return self.session.query(User).filter_by(is_approved=False).all()
        
    def approve_user(self, user_id: int) -> User:
        user = self.get_user_by_id(user_id)
        if user:
            user.is_approved = True
            self.session.commit()
            self.session.refresh(instance=user)
        return user
        
    def suspend_user(self, user_id: int) -> User:
        user = self.get_user_by_id(user_id)
        if user:
            user.is_approved = False
            self.session.commit()
            self.session.refresh(instance=user)
        return user

    def update_user(self, user_id: int, data) -> User:
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        if data.first_name is not None:
            user.first_name = data.first_name
        if data.last_name is not None:
            user.last_name = data.last_name
        if data.email is not None:
            user.email = data.email
        if data.password:
            user.password = data.password  # already hashed by UserService
        self.session.commit()
        self.session.refresh(instance=user)
        return user

    def delete_user(self, user_id: int) -> bool:
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        self.session.delete(user)
        self.session.commit()
        return True