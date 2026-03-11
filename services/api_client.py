import requests

BASE_URL = "http://127.0.0.1:8000"

class APIClient:

    def login(self, username, password):
        response = requests.post(
            f"{BASE_URL}/auth/login",
            data={
                "username": username,
                "password": password
            }
        )

        if response.status_code == 200:
            return response.json()
        else:
            return None