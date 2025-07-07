from datetime import time, datetime


class WeekTimeWindow:
    def __init__(self, weekday: int, start_time: time, end_time: time):
        if not (0 <= weekday <= 6):
            raise ValueError(f"'{weekday}' is not a valid weekday number (0=Monday,.., 6=Sunday).")
        if start_time >= end_time:
            raise ValueError("Start time must be before end time.")
        
        self._weekday = weekday
        self.start_time = start_time
        self.end_time = end_time

    def __repr__(self):
        return f"WeekTimeWindow(weekday={self.weekday}, start_time={self.start_time}, end_time={self.end_time})"
    
    def __str__(self) -> str:
        return self.__repr__()
    
    def contains(self, dt: datetime) -> bool:
        return dt.weekday() == self._weekday and self.start_time <= dt.time() <= self.end_time
    
    @property
    def weekday(self) -> str:
        return ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][self._weekday]