from ..sampling import Sampler


class ServerProcess():
    """One service slot of a server; ``delay_strategy`` is the server's bound sampler."""

    def __init__(self, my_server, delay_strategy):
        from ..Items.item import Item # Lazy import to avoid recircularity
        from .multiServer import MultiServer # Lazy import to avoid recircularity

        self.delay_strategy: Sampler = delay_strategy

        self.my_server:MultiServer=my_server
        self.the_item:Item=None
        self.phase = None        # None | "waiting" (resources) | "setup" | "processing"
        self.last_type = None    # type of the last item processed (setup changes)
        self.work = None         # WorkHandle of the current setup/service
        self.allocation = None   # resource units held (PyFlow.resources.Allocation)
        self.request = None      # pending resource request, if waiting

    def get_delay(self)->float:
        return self.delay_strategy.sample(self.the_item)
    
    def execute(self) -> None:
        self.my_server.complete_server_process(self)

    def get_item(self):
        return self.the_item
    
    def set_item(self, the_item):
        self.the_item = the_item
