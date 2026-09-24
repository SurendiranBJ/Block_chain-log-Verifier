from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from bson.objectid import ObjectId

class Database:
    def __init__(self, uri="mongodb://localhost:27017/", db_name="logchain_db"):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        
        self.users = self.db.users
        self.logs = self.db.logs
        self.activities = self.db.activities
        
        # Ensure indexes (as recommended in DEPLOYMENT.md)
        self.users.create_index("username", unique=True)
        self.logs.create_index([("user_id", 1), ("is_active", 1)])
        self.activities.create_index([("user_id", 1), ("timestamp", -1)])

    # --- USER OPERATIONS ---
    
    def create_user(self, username, password, email="", role="user"):
        if self.users.find_one({"username": username}):
            return None, "Username already exists"
            
        user_doc = {
            "username": username,
            "password": generate_password_hash(password),
            "email": email,
            "role": role,
            "is_active": True,
            "created_at": datetime.now(),
            "last_login": None
        }
        result = self.users.insert_one(user_doc)
        return str(result.inserted_id), None

    def get_user_by_username(self, username):
        return self.users.find_one({"username": username})

    def get_user_by_id(self, user_id):
        try:
            return self.users.find_one({"_id": ObjectId(user_id)})
        except:
            return None

    def get_all_users(self):
        return list(self.users.find())

    def update_login_time(self, user_id):
        self.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"last_login": datetime.now()}}
        )

    def toggle_user_status(self, user_id):
        user = self.get_user_by_id(user_id)
        if user:
            new_status = not user.get("is_active", True)
            self.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"is_active": new_status}}
            )
            return new_status
        return None

    def delete_user(self, user_id):
        # Delete user and all associated logs and activities
        self.logs.delete_many({"user_id": str(user_id)})
        self.activities.delete_many({"user_id": str(user_id)})
        result = self.users.delete_one({"_id": ObjectId(user_id)})
        return result.deleted_count > 0

    def verify_password(self, hashed_password, raw_password):
        return check_password_hash(hashed_password, raw_password)

    # --- LOG OPERATIONS ---

    def add_log_source(self, user_id, log_path, case_id, description=""):
        log_doc = {
            "user_id": str(user_id),
            "log_path": log_path,
            "case_id": case_id,
            "description": description,
            "is_active": True,
            "created_at": datetime.now(),
            "last_checked": None,
            "total_entries": 0,
            "verified_entries": 0
        }
        result = self.logs.insert_one(log_doc)
        return str(result.inserted_id), None

    def get_logs_for_user(self, user_id):
        return list(self.logs.find({"user_id": str(user_id)}))

    def get_active_logs(self):
        return list(self.logs.find({"is_active": True}))

    def get_all_logs(self):
        return list(self.logs.find())

    def update_log_stats(self, log_id, total, verified, tampered_lines=None):
        update_data = {
            "total_entries": total,
            "verified_entries": verified,
            "last_checked": datetime.now()
        }
        if tampered_lines is not None:
            update_data["tampered_lines"] = tampered_lines
            
        self.logs.update_one(
            {"_id": ObjectId(log_id)},
            {"$set": update_data}
        )

    def toggle_log_status(self, log_id, user_id=None):
        query = {"_id": ObjectId(log_id)}
        if user_id:
            query["user_id"] = str(user_id)
            
        log = self.logs.find_one(query)
        if log:
            new_status = not log.get("is_active", True)
            self.logs.update_one(query, {"$set": {"is_active": new_status}})
            return new_status
        return None
        
    def delete_log(self, log_id, user_id=None):
        query = {"_id": ObjectId(log_id)}
        if user_id:
            query["user_id"] = str(user_id)
        result = self.logs.delete_one(query)
        return result.deleted_count > 0

    # --- ACTIVITY OPERATIONS ---

    def log_activity(self, user_id, action, details="", case_id=None):
        activity_doc = {
            "user_id": str(user_id) if user_id else "SYSTEM",
            "action": action,
            "details": details,
            "timestamp": datetime.now()
        }
        if case_id:
            activity_doc["case_id"] = case_id
        self.activities.insert_one(activity_doc)

    def get_recent_activities(self, limit=50):
        return list(self.activities.find().sort("timestamp", -1).limit(limit))

    def get_user_activities(self, user_id, limit=50):
        return list(self.activities.find({"user_id": str(user_id)}).sort("timestamp", -1).limit(limit))
