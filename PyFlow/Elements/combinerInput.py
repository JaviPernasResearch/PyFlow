from collections import deque

from ..Items.item import Item
from ..SimClock.simClock import SimClock
from .element import Element
from .arrivalListener import ArrivalListener
from .inputStrategy import InputStrategy, DefaultStrategy


class CombinerInput(Element):
    def __init__(self, capacity: int, arrival_listener: ArrivalListener, input_id: int, name: str, 
                 sim_clock: SimClock, input_strategy: InputStrategy = DefaultStrategy()):
        super().__init__(name, sim_clock)
        self.capacity = capacity
        self.current_items = 0
        self.input_id = input_id
        self.items_queue = deque()
        self.arrival_listener = arrival_listener
        self.input_strategy = input_strategy  # Store the strategy

    def start(self):
        self.items_queue.clear()
        self.current_items = 0

    def release(self, quantity: int) -> deque:
        released_items = deque()

        for _ in range(quantity):
            if self.items_queue:
                item = self.items_queue.popleft()
                released_items.append(item)
                self.current_items -= 1

        return released_items

    def get_queue_length(self) -> int:
        return self.current_items

    def get_free_capacity(self) -> int:
        return self.capacity - self.current_items

    def unblock(self) -> bool:
        self.get_input().notify_available()
        return True

    def receive(self, item: Item) -> bool:
        if self.check_availability(item):
            self.current_items += 1
            item.set_constrained_input(self.input_id)  # Asigna la entrada al elemento
            self.items_queue.append(item)

            # Notifica al ArrivalListener que se ha recibido un nuevo elemento
            if not self.arrival_listener.component_received(item, self.input_id):
                self.get_input().notify_available()
            
            return True
        
        return False

    def check_availability(self, item: Item) -> bool:
        return (self.current_items < self.capacity or self.capacity < 0) and self.arrival_listener.is_main_receiving() and self.input_strategy.is_valid(item)

    def get_capacity(self) -> int:
        return self.capacity
    
    def set_capacity(self, capacity:int) -> None:
        self.capacity = capacity

    def get_items(self) -> deque:
        return self.items_queue

