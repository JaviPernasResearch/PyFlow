from typing import Protocol

class Event(Protocol):
    def  execute(self) ->None:
        raise NotImplementedError ('Subclasses must implement this method.')