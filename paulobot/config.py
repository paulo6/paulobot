import json
import os


DEFAULT_CONFIG = "~/.paulobot.json"

DEFAULT_TIMEOUT = 180

class ConfigError(Exception):
    def __init__(self, error, field, object_name):
        self.error = error
        self.field = field
        self.object_name = object_name

    def __str__(self):
        msg = f"{self.error} '{self.field}'"
        if self.object_name:
            msg += f" in {self.object_name}"
        return msg

class json_field(object):
    """
    Descriptor (non-data) for building an attribute on-demand on first use from
    the JSON.
    """
    
    def __init__(self, field, default=None, mandatory=False, list_cls=None):
        self._attr_name = None
        self._field = field
        self._default = default
        self._mandatory = mandatory
        self._list_cls = list_cls

    def __call__(self, fn):
        self._attr_name = fn.__name__
        return self

    def __get__(self, inst, cls):
        # Check whether field is mandatory and present
        if self._mandatory and self._field not in inst.data:
            raise ConfigError(f"Missing mandatory field",
                              self._field, inst._object_name)

        # Get field from JSON data
        attr = inst.data.get(self._field, self._default)

        # If we have a list class, then initialize each element
        # of the list with it.
        if self._list_cls is not None:
            if not isinstance(attr, list):
                raise ConfigError(f"Expected list for",
                                  self._field, inst._object_name)
            attr = [self._list_cls(a) for a in attr]

        # Now we have the value, store it for future calls
        setattr(inst, self._attr_name, attr)

        return attr


class _Base:
    def __init__(self, data):
        self.data = data
        self.parent = None

        # Trigger all the json field properites to read the
        # JSON and validate fields
        for name, val in self.__class__.__dict__.items():
            if isinstance(val, json_field):
                getattr(self, name)

    @property
    def _object_name(self):
        return None


class Area(_Base):
    @property
    def _object_name(self):
        return f"Area {self.data.get('name')}"

    @json_field("name", mandatory=True)
    def name(self):
        pass

    @json_field("description", default="")
    def desc(self):
        pass

    @json_field("size", default=1)
    def size(self):
        pass


class Sport(_Base):
    @property
    def _object_name(self):
        return f"Area {self.data.get('name')}"

    @json_field("name", mandatory=True)
    def name(self):
        pass

    @json_field("description", default="")
    def desc(self):
        pass

    @json_field("team-size", mandatory=True)
    def team_size(self):
        pass

    @json_field("area")
    def area(self):
        pass


class Location(_Base):
    @property
    def _object_name(self):
        return f"Location {self.data.get('name')}"

    @json_field("name", mandatory=True)
    def name(self):
        pass

    @json_field("room")
    def room(self):
        pass

    @json_field("areas", default=[], list_cls=Area)
    def areas(self):
        pass

    @json_field("sports", mandatory=True, list_cls=Sport)
    def sports(self):
        pass


class Config(_Base):
    def __init__(self):
        data = self._load_config(os.path.expanduser(DEFAULT_CONFIG))
        super().__init__(data)

    def _load_config(self, path):
        if not os.path.exists(path):
            raise Exception(f"Cannot find config file {path}")

        with open(path, 'r') as f:
            data = json.load(f)
        return data

    @json_field("token", mandatory=True)
    def token(self):
        pass

    @json_field("admins", default=[], list_cls=str)
    def admins(self):
        pass

    @json_field("notify", default=[], list_cls=str)
    def notify_list(self):
        pass

    @json_field("locations", default=[], list_cls=Location)
    def locations(self):
        pass

    @json_field("ready-timeout", default=180)
    def ready_timeout(self):
        pass

    @json_field("idle-time", default=120)
    def idle_time(self):
        pass
