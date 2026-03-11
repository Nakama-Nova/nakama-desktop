from services.api_client import APIClient
from services.session import Session

api = APIClient()

def login(username, password):
    result = api.login(username, password)

    if result:
        Session.token = result["access_token"]

    return result