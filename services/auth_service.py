from services.api_client import APIClient

api = APIClient()

def login(username, password):
    return api.login(username, password)