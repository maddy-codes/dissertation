import json
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=True) # Nullable for Xero SSO only users
    
    # Xero Integration attributes
    xero_user_id = db.Column(db.String(100), unique=True, nullable=True)
    xero_token_data = db.Column(db.Text, nullable=True) # Store JSON token dict string
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_xero_token(self, token_dict: dict):
        self.xero_token_data = json.dumps(token_dict)
        
    def get_xero_token(self) -> dict:
        if self.xero_token_data:
            return json.loads(self.xero_token_data)
        return None
