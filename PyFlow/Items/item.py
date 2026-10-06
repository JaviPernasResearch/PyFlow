from typing import List, Optional


class Item:
    # Legacy process-wide counter, only used for items created without ``item_id``
    # (e.g. directly by user code). Elements stamp items with a per-model id instead.
    ITEM_NUMBER: int = 0

    def __init__(self, creation_time: float, name: Optional[str] = None, item_type: Optional[str] = None,
                 labels: Optional[dict] = None, model_item: bool = False, *, item_id: Optional[int] = None,
                 priority: int = 0):
        if item_id is None:
            if not model_item:
                Item.ITEM_NUMBER += 1
            item_id = Item.ITEM_NUMBER
        self.item_number = item_id  # unique within its model. Must not be changed.
        self.creation_time: float = creation_time
        self.name: str = name if name is not None else f"Item{item_id}"
        self.type: str = item_type if item_type is not None else "Default"
        self.input_id = None
        self.labels = labels if labels is not None else {}
        self.priority: int = priority
        self.sub_items: List["Item"] = []

    def copy_model(self, creation_time: float, name: Optional[str] = None, *, item_id: Optional[int] = None) -> 'Item':
        return Item(creation_time, name, self.type, self.labels.copy(), item_id=item_id, priority=self.priority)

    def add_item(self, the_item: "Item") -> None:
        """Attach a component (batch mode of Combiner / MultiAssembler)."""
        self.sub_items.append(the_item)

    def get_sub_items(self) -> List["Item"]:
        return self.sub_items

    def set_type(self,type:int)->None:
        self.type=type

    def get_creation_time(self)->float:
        return self.creation_time

    def get_type(self)->int:
        return self.type

    def set_constrained_input(self, input_id:int):
        self.input_id=input_id

    def get_input_id(self):
        return self.input_id

    def set_label_value(self, label_name: str, value):
        """Dynamically add or update a label."""
        self.labels[label_name] = value

    def get_label_value(self, label_name: str):
        """Retrieve the value of a label, or None if it doesn't exist."""
        return self.labels.get(label_name)

    def get_all_labels(self):
        """Retrieve all labels and their values."""
        return self.labels

    def add_label(self, label_name: str, value):
        """Add a new label or update an existing label."""
        self.labels[label_name] = value

    def remove_label(self, label_name: str):
        """Remove a label if it exists."""
        if label_name in self.labels:
            del self.labels[label_name]

    _FIELDS = frozenset({"type", "name", "priority", "creation_time", "item_number"})

    def expression_field(self, name: str):
        """Fields reachable from expressions (``value.type``, ``value.PT``): the item
        attributes above, otherwise the label of that name (``None`` if missing)."""
        if name in Item._FIELDS:
            return getattr(self, name)
        return self.labels.get(name)

    def __repr__(self) -> str:
        return f"Item({self.name!r}, id={self.item_number}, type={self.type!r})"
