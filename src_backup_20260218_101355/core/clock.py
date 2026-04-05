import time

class TimeSync:
    def __init__(self):
        self.offset_ms = 0

    def set_offset(self, server_time_ms: int):
        local_ms = int(time.time() * 1000)
        self.offset_ms = server_time_ms - local_ms

    def now_ms(self) -> int:
        return int(time.time() * 1000) + int(self.offset_ms)
