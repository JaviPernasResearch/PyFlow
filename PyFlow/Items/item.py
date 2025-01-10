from typing import Optional


class Item:
    ITEM_NUMBER:int=0

    def __init__(self, creation_time: float, item_type: Optional[str] = None, labels: Optional[dict] = None):
        Item.ITEM_NUMBER += 1
        self.creation_time: float = creation_time
        self.type: str = item_type if item_type is not None else "Default"
        self.input_id = None
        self.labels = labels if labels is not None else {}

    def copy_with_new_creation_time(self, creation_time: float) -> 'Item':
        return Item(creation_time, self.type, self.labels.copy())

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

    def set_label(self, label_name: str, value):
        """Dynamically add or update a label."""
        self.labels[label_name] = value

    def get_label(self, label_name: str):
        """Retrieve the value of a label, or None if it doesn't exist."""
        return self.labels.get(label_name)

    def get_all_labels(self):
        """Retrieve all labels and their values."""
        return self.labels