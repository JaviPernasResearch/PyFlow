import openpyxl #Esto é para poder usar archivos Excel en Python
from typing import Optional, List

from SimClock.SimClock import SimClock
from Items.item import Item
from Elements.Element import Element
#from SimClock.Event import Event

class ScheduleSource(Element):
    def __init__(self, name: str, clock: SimClock, file_name: str):
        super().__init__(name, clock)
        self.file_name = file_name
        self.last_item: Optional[Item] = None
        self.number_items: int = 0
        self.workbook = openpyxl.load_workbook(file_name)
        self.sheet = self.workbook.active
        self.row_iterator = self.sheet.iter_rows(values_only=True)

    def start(self) -> None:
        self.number_items = 0
        self.clock.schedule_event(self, 0.0)
        output = self.get_output()
        if output is None:
            print(f"Warning: Output is not set for ScheduleSource {self.name}.")

    def unblock(self) -> bool:
        new_item = self.create_item()
        if new_item and self.get_output().send(new_item):
            self.last_item = new_item
            self.number_items += 1
            return True
        return False

    def get_number_items(self):
        return self.number_items

    def receive(self, the_item: Item) -> bool:
        raise NotImplementedError("The Source cannot receive Items.")

    def execute(self) -> None:
        new_item = self.create_item()
        if new_item:
            self.last_item = new_item
            self.number_items += 1

            while self.get_output().send(self.last_item):
                new_item = self.create_item()
                if new_item:
                    self.last_item = new_item
                    self.number_items += 1
                else:
                    break
        else:
            print(f"No more items to create from Excel for ScheduleSource {self.name}.")

    def check_availability(self, the_item: Item) -> bool:
        return True

    def create_item(self) -> Optional[Item]:
        try:
            row = next(self.row_iterator)
            if not row:
                raise StopIteration("End of file reached")

            creation_time = float(row[3]) if row[3] is not None else self.clock.get_simulation_time()
            item = Item(creation_time)
            item.set_type((row[0]))
            return item
        except StopIteration:
            print(f"End of Excel file reached for ScheduleSource {self.name}")
            self.workbook.close()
            return None

    def get_queue_length(self) -> int:
        return 0

    def get_free_capacity(self) -> int:
        return 0

    