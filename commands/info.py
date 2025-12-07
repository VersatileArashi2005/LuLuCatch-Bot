from db import get_user_by_id

async def info_cmd(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return f"User {user_id} not found."
    
    first_name = user.get("first_name", "Unknown")
    role = user.get("role", "user")
    last_catch = user.get("last_catch", "None")
    
    return f"User Info:\nName: {first_name}\nRole: {role}\nLast Catch: {last_catch}"

