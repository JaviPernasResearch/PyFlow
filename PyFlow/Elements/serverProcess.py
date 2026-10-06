from ..sampling import Sampler, as_sampler
from .state import State


class ServerProcess():
    """One service slot of a server. ``delay_strategy`` is the server's sampler; a raw
    specification is accepted for backwards compatibility and bound to the server's model."""

    def __init__(self, my_server, delay_strategy):
        from ..Items.item import Item # Lazy import to avoid recircularity
        from .multiServer import MultiServer # Lazy import to avoid recircularity

        if isinstance(delay_strategy, Sampler) and delay_strategy.rng is not None:
            self.delay_strategy = delay_strategy
        elif hasattr(my_server, "_bind_sampler"):
            self.delay_strategy = my_server._bind_sampler(delay_strategy, "service")
        else:
            self.delay_strategy = as_sampler(delay_strategy)

        self.my_server:MultiServer=my_server
        self.the_item:Item=None
        self.phase = None        # None | "waiting" (resources) | "setup" | "processing"
        self.last_type = None    # type of the last item processed (setup changes)
        self.work = None         # WorkHandle of the current setup/service
        self.allocation = None   # resource units held (PyFlow.resources.Allocation)
        self.request = None      # pending resource request, if waiting
        self.state:State=State.IDLE  #0:idle, 1:receiving, 3: busy, 4 blocked

    def get_delay(self)->float:
        return self.delay_strategy.get_delay(self.the_item)
    
    def execute(self) -> None:
        self.my_server.complete_server_process(self)

    def get_state(self) -> State:
        return self.state
    
    def set_state(self, new_state:State) -> None:
        self.state = new_state 

    def get_item(self):
        return self.the_item
    
    def set_item(self, the_item):
        self.the_item = the_item
