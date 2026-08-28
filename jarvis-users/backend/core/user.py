from backend.auth.current_user import get_current_user


def get_user():
    """Return only the authenticated SaaS profile for the current request."""
    user = get_current_user()
    return {
        "id": user.get("id"),
        "supabase_user_id": user.get("supabase_user_id"),
        "email": user.get("email"),
        "display_name": user.get("display_name"),
        "role": user.get("role"),
        "status": user.get("status"),
        "onboarding_completed": user.get("onboarding_completed", False),
        "subscription": user.get("subscription"),
    }
