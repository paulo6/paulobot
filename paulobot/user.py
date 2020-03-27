class User:
    def __init__(self, pb, name, email):
        self.name = name
        self.email = email
        self._pb = pb

    @property
    def is_admin(self):
        return False

    def send_msg(self, text, markdown=None):
        self._pb.send_message(text=text, markdown=markdown,
                              user_email=self.email)

    def update_last_msg(self):
        pass


class UserManager:
    def __init__(self, pb):
        self._pb = pb
        self._users = {}

    def lookup_user(self, email):
        return self._users.get(email)

    def create_user(self, name, email):
        if email in self._users:
            return Exception(f"User {email} already exists!")

        self._users[email] = User(self._pb, name, email)