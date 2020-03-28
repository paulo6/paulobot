class User:
    def __init__(self, pb, email, full_name, first_name):
        self.email = email
        self.full_name = full_name
        self.first_name = first_name
        self.locations = set()
        self._pb = pb

    def __hash__(self):
        return hash(self.email)

    def __str__(self):
        return self.email

    def __repr__(self):
        return f"<User({self.email})>"

    @property
    def is_admin(self):
        return self.email in self._pb.admins

    @property
    def name(self):
        return self.first_name if self.first_name else self.full_name

    @property
    def username(self):
        return self.email.split("@")[0]

    def send_msg(self, text, markdown=None):
        self._pb.send_message(text=text, markdown=markdown,
                              user_email=self.email)

    def update_last_msg(self, update_idle_games=False):
        pass


class UserManager:
    def __init__(self, pb):
        self._pb = pb
        self._users = {}

    def lookup_user(self, email):
        return self._users.get(email)

    def create_user(self, email, full_name, first_name):
        if email in self._users:
            return Exception(f"User {email} already exists!")

        user = User(self._pb, email, full_name, first_name)
        self._users[email] = user

        self._pb.loc_manager.add_user_to_locations(user)
        return user