import pyraco

from gamest import db
from gamest.plugins import IdentifierPlugin


class RetroarchProcess:
    def __init__(self, crc32, plugin):
        self.crc32 = crc32
        self.plugin = plugin
        self.failures = 0
        self.paused = 0

    def is_running(self):
        try:
            status = self.plugin._conn.get_status()
        except Exception:
            self.failures += 1
            if self.failures > 6:
                # If we haven't gotten a response in the last 30 seconds, probably
                # retroarch is closed.
                return False
            return True

        self.failures = 0

        if status.crc32 != self.crc32:
            return False

        # Retroarch should tell us if the game is paused, but it doesn't do that
        # if the game was paused by opening the menu. Therefore, this isn't
        # totally accurate.
        if status.status == 'PAUSED':
            self.paused += 1
            # Consider the game stopped if it has been paused for five minutes straight.
            return self.paused <= 60
        elif status.status == 'PLAYING':
            self.paused = 0
            return True
        else:
            self.plugin.logger.error("Unknown status: %r", status.status)
            return False


class RetroarchIdentifierPlugin(IdentifierPlugin):
    SETTINGS_TAB_NAME = "Retroarch"

    def __init__(self, application):
        super().__init__(application)

        self._conn = pyraco.Connection(
            self.config.get('host', fallback='localhost'),
            self.config.get('port', type=int, fallback=55355))

        self.logger.debug("RetroarchIdentifierPlugin initialized."
                          "\n\thost: %r"
                          "\n\tport: %r",
                          self.config.get('host', fallback='localhost'),
                          self.config.get('port', type=int, fallback=55355))

    @classmethod
    def get_settings_template(cls):
        d = super().get_settings_template()

        d[(cls.__name__, 'host')] = {
            'name': 'Host',
            'type': 'text',
            'default': 'localhost',
            'hint': 'The name or IP of the host running retroarch.',
        }

        d[(cls.__name__, 'port')] = {
            'name': 'Port',
            'type': int,
            'default': '55355',
            'hint': 'The port used by retroarch.',
        }

        d[(cls.__name__, 'auto_add')] = {
            'name': 'Automatically add games',
            'type': 'bool',
            'default': False,
            'hint': ('If checked, any unrecognized game running in retroarch '
                     'will be added and tracked automatically.'),
        }

        return d

    def candidates(self):
        try:
            status = self._conn.get_status()
        except (ConnectionRefusedError, ConnectionResetError):
            return []
        except Exception:
            self.logger.exception("Exception in candidates.")
            return []

        if not status.game:
            return []

        return [db.UserApp(
            note=status.game,
            identifier_plugin=self.__class__.__name__,
            identifier_data='crc32='+status.crc32)]

    def identify_game(self):
        try:
            status = self._conn.get_status()
        except (ConnectionRefusedError, ConnectionResetError):
            return None
        except Exception:
            self.logger.exception("Exception in identify_game.")
            return None

        if not status:
            return None

        if status.status == 'CONTENTLESS':
            return None
        if status.status != 'PLAYING':
            self.logger.debug("Found a game, but status is not 'PLAYING': %r", status)
            return None

        app = db.Session.query(db.UserApp).\
            filter(
                db.UserApp.identifier_plugin == self.__class__.__name__,
                db.UserApp.identifier_data == 'crc32='+status.crc32).\
            first()

        if app:
            self.logger.debug("Found app: %r", app)
            return (RetroarchProcess(status.crc32, self), app)
        elif self.config.getboolean('auto_add', fallback=False):
            user_app = db.UserApp(
                identifier_plugin=self.__class__.__name__,
                identifier_data='crc32='+status.crc32,
                app=db.App(name=status.game))
            db.Session.add(user_app)
            self.logger.info("Automatically adding new app: %r", user_app)
            return (RetroarchProcess(status.crc32, self),
                    user_app)

        return None
