class Cron:
    """
    Simpler representation of a cadence with a very specific day/time pair.
    Used for constructing a Timeline. A timeline is expected to have 28 days
    to fit all cadences accordingly.

    Attributes
    ----------
    day: int
        Representation of day out of 28 (max days in a Timeline month)
    hour: int
        Representation of hours in a day (0-23)
    """
    def __init__(self, day: int, hour: int):
        if 0 > day > Cron.days_in_a_month() - 1:
            raise IndexError(f"Day out of range: {day}")
        if 0 > hour > Cron.hours_in_a_day() - 1:
            raise IndexError(f"Hour out of range: {hour}")
        self.day = day
        self.hour = hour

    @staticmethod
    def weeks_in_month() -> int:
        return 4

    @staticmethod
    def days_in_a_week() -> int:
        return 7

    @staticmethod
    def days_in_a_month() -> int:
        return 28

    @staticmethod
    def hours_in_a_day() -> int:
        return 24

    def __hash__(self):
        return hash(f"{self.day}_{self.hour}")

    def __eq__(self, other):
        return self.day == other.day and self.hour == other.hour

    def __le__(self, other):
        return ((self.hour + (self.day * self.hours_in_a_day())) <=
                (other.hour + (other.day * self.hours_in_a_day())))

    def __lt__(self, other):
        return ((self.hour + (self.day * self.hours_in_a_day())) <
                (other.hour + (other.day * self.hours_in_a_day())))

    def __str__(self):
        from gopos.cadences.cadence import Cadence
        return f"{self.day} ({Cadence.DAY_LIST[self.day % self.days_in_a_week()]}) at {self.hour}:00"

    def __repr__(self):
        return str(self)
