def get_current_user():

    return {
        "id": 1,
        "email": "gatotico99@gmail.com",
        "role": "owner",
        "status": "active"
    }


def get_current_user_id():
    return get_current_user()["id"]