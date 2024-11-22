from typing import Protocol, List

class Event(Protocol):
    def  execute(self) ->None:
        raise NotImplementedError ('Subclasses must implement this method.')