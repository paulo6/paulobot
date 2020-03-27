class Sport:
    def __init__(self, name, desc, has_scores, area):
        self.name = name
        self.desc = desc
        self.has_scores = has_scores
        self.area = area


class Area:
    def __init__(self, name, desc):
        self.name = name
        self.desc = desc


class Location:
    def __init__(self, pb, name):
        self._pb = pb
        self.name = name
        self.sports = {}
        self.areas = {}


class LocationManager:
    def __init__(self, pb):
        self._pb = pb
        self.locations = {}

    def get_user_locations(self, user):
        return []
    