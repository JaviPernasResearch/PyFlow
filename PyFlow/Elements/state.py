from enum import Enum

class State(Enum):
    IDLE = 1
    RECEIVING = 2
    BUSY = 3
    BLOCKED = 4