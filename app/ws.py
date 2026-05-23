class ConnectionManager:
    def __init__(self):
        self._connections: dict = {}

    def is_online(self, username: str) -> bool:
        return username in self._connections


manager = ConnectionManager()
