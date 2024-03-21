class Cron:
    def __init__(self, day: int, hour: int):
        if 0 > day > 28:
            raise IndexError(f"Day out of range: {day}")
        if 0 > hour > 23:
            raise IndexError(f"Hour out of range: {hour}")
        self.day = day
        self.hour = hour

    @staticmethod
    def weeks_in_month():
        return 4

    @staticmethod
    def days_in_a_week():
        return 7

    @staticmethod
    def days_in_a_month():
        return 28

    @staticmethod
    def hours_in_a_day():
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
