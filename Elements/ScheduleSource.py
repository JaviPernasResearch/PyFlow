import openpyxl #Esto é para poder usar archivos Excel en Python
from typing import Optional, List

from SimClock.SimClock import SimClock
from Items.item import Item
from Elements.Element import Element

class ScheduleSource(Element):
    def __init__(self, name: str, clock: SimClock, file_name: str):
        super().__init__(name, clock)
        self.file_name = file_name
        self.last_item: Optional[Item] = None
        self.number_items: int = 0
        self.workbook = openpyxl.load_workbook(file_name)
        self.sheet = self.workbook.active
        self.row_iterator = self.sheet.iter_rows(values_only=True)
        self.current_quantity: int = 0
        self.current_arrival_time: float = 0
        self.current_item_name: str = ""

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
            if self.current_quantity <= 0:
                row = next(self.row_iterator)
            if not row:
                raise StopIteration("End of file reached")

            self.current_arrival_time = float(row[0]) if row[0] is not None else self.clock.get_simulation_time()
            self.current_item_name = str(row[1]) if row[1] is not None else "Default"
            self.current_quantity = int(row[2]) if row[2] is not None else 1

            self.current_quantity -= 1
            item = Item(self.current_arrival_time)
            item.set_type(self.current_item_name)
            return item
        except StopIteration:
            self.workbook.close()
            return None

    def get_queue_length(self) -> int:
        return 0

    def get_free_capacity(self) -> int:
        return 0

    