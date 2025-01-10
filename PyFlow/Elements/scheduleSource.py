from collections import deque
import openpyxl #Esto é para poder usar archivos Excel en Python
from typing import Optional, List

from ..Items.item import Item
from ..SimClock.simClock import SimClock
from .source import Source

class ScheduleSource(Source):
    def __init__(self, name: str, clock: SimClock, file_name: str, model_item: Optional[Item] = None):
        super().__init__(name, clock, model_item)
        self.file_name = file_name
        self.workbook = openpyxl.load_workbook(file_name)
        self.sheet = self.workbook.active
        self.row_iterator = self.sheet.iter_rows(values_only=True)
        self.row = None
        self.current_pending_q = 0
        self.current_arrival_time = 0
        self.current_item_name = None
        self.blocked_items = deque()

    def start(self) -> None:
        self.schedule_next_arrival()    

    def schedule_next_arrival(self) -> None:
        try:
            row = next(self.row_iterator)
            self.row = row
            if not row or row[0] is None:
                raise StopIteration("End of file reached")

            self.current_arrival_time = float(row[0]) if row[0] is not None else self.clock.get_simulation_time()
            self.current_item_name = str(row[1]) if row[1] is not None else "Default"
            self.current_pending_q = int(row[2]) if row[2] is not None else 1

            delay = max(0, self.current_arrival_time - self.clock.get_simulation_time())
            self.clock.schedule_event(self, delay)

        except StopIteration:
            self.workbook.close()

    def unblock(self) -> None:
        while self.blocked_items:
            item = self.blocked_items.popleft()
            if self.get_output().send(item):
                self.number_items += 1
            else:
                self.blocked_items.appendleft(item)
                break

    def receive(self, the_item: Item) -> bool:
        raise NotImplementedError("The Source cannot receive Items.")

    def execute(self) -> None:
        new_item = self.create_item()
        while new_item:
            if not self.get_output().send(new_item):
                self.blocked_items.append(new_item)

            self.number_items += 1
            new_item = self.create_item()
        self.schedule_next_arrival()

    def check_availability(self, the_item: Item) -> bool:
        return True

    def create_item(self) -> Optional[Item]:
        if self.current_pending_q <= 0:
            return None

        self.current_pending_q -= 1
        item = super().create_item(name = self.current_item_name)
        item.set_type(self.current_item_name)

        for idx, value in enumerate(self.row[3:], start=3):
            if value is not None:
                item.set_label(f"label_{idx}", value)

        return item
    