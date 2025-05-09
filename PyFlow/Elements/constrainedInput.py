from collections import deque

from ..Items.item import Item
from ..SimClock.simClock import SimClock
from .element import Element
from .arrivalListener import ArrivalListener


class ConstrainedInput(Element):
    def __init__(self, capacity: int, arrival_listener: ArrivalListener, input_id: int, name: str, sim_clock: SimClock):
        super().__init__(name, sim_clock)
        self.capacity = capacity
        self.current_items = 0
        self.input_id = input_id
        self.items_queue = deque(maxlen=capacity)
        self.arrival_listener = arrival_listener

    def start(self):
        self.items_queue.clear()
        self.current_items = 0

    def release(self, quantity: int) -> deque:
        released_items = deque()

        for _ in range(quantity):
            if self.items_queue:
                the_item = self.items_queue.popleft()
                released_items.append(the_item)
                self.current_items -= 1

                self.get_input().notify_available()

        return released_items

    def get_queue_length(self) -> int:
        return self.current_items

    def unblock(self) -> bool:
        return True

    def receive(self, the_item: Item) -> bool:
        if self.current_items < self.capacity or self.capacity < 0:
            self.current_items += 1
            the_item.set_constrained_input(self.input_id)  # Asigna la entrada al elemento
            self.items_queue.append(the_item)

            # Notifica al ArrivalListener que se ha recibido un nuevo elemento
            self.arrival_listener.component_received(the_item, self.input_id)
            
            return True
        else:
            return False

    def check_availability(self, the_item: Item) -> bool:
        return self.current_items < self.capacity or self.capacity < 0

    def get_capacity(self) -> int:
        return self.capacity

    def get_items(self) -> deque:
        return self.items_queue
        

