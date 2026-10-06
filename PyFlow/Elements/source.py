# FILE: PyFlow/Elements/source.py
from abc import abstractmethod
from collections import deque
from typing import TYPE_CHECKING, Optional

from ..Items.item import Item
from .element import Element

if TYPE_CHECKING:
    from ..model import Model

class Source(Element):
    def __init__(self, name: str, model: "Model", model_item: Optional[Item] = None):
        super().__init__(name, model)

        self.model_item = model_item
        self.last_items = deque()
        self.number_items = 0

    @abstractmethod
    def start(self) -> None:
        pass

    @abstractmethod
    def execute(self) -> None:
        pass

    def create_item(self, name: Optional[str] = None) -> Item:
        item_id = self.model.next_item_id()
        if self.model_item:
            return self.model_item.copy_model(self.clock.get_simulation_time(), name, item_id=item_id)
        return Item(self.clock.get_simulation_time(), name, item_id=item_id)
