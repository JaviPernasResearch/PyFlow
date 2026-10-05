import logging
from typing import List, Optional

from ..Elements.element import Element
from ..Items.item import Item
from .link import Link
from .outputStrategy import OutputContext, OutputStrategy, FirstAvailableStrategy

logger = logging.getLogger("pyflow")


##General Links are defined per element and per input and output lists (thus, 2 links per element connected upstream and downstream)
class GeneralLink (Link):
    """Connects origins to destinations (SimuLean ``GeneralLink``).

    ``send``: refused if the origin is stopped (output blocked); otherwise the origin's
    output strategy picks a destination among those that ``can_accept(item, origin)``
    (capacity, not stopped, input strategy). Statistics are recorded only if the destination
    really receives the item. Refused origins are remembered and get priority (FIFO) in
    ``notify_available``.
    """

    def __init__(self, origins:List[Element], destinations:List[Element], strategy: OutputStrategy = None):
        self.origins:List[Element]=origins
        self.destinations:List[Element]=destinations
        self._strategy = strategy
        self._context: Optional[OutputContext] = None
        # Origins blocked waiting for space, shared by all links of the same model
        self.pending_requests = origins[0].model.pending_requests

    @property
    def strategy(self) -> OutputStrategy:
        """The origin's output strategy (falls back to the one given to this link)."""
        return self.origins[0].output_strategy or self._strategy or FirstAvailableStrategy()

    def _wait(self, origin: Element) -> bool:
        if origin not in self.pending_requests:
            self.pending_requests.append(origin)
        return False

    # Thus, at "send", there will be only one origin in the current link.
    def send(self, the_item:Item, origin: Optional[Element] = None)->bool:
        origin = origin or self.origins[0]
        if origin._output_blocks:  # stopped: keep the item, retried on resume
            return self._wait(origin)

        destinations = self.destinations
        context = self._context
        if context is None or context.source is not origin or context.outputs is not destinations:
            context = self._context = OutputContext(origin, destinations)
        index_destination = self.strategy.select(destinations, the_item, context)
        if not 0 <= index_destination < len(destinations):
            return self._wait(origin)
        target = destinations[index_destination]
        # Custom strategies may skip the check: never deliver to a destination that refuses
        if not target.can_accept(the_item, origin):
            return self._wait(origin)

        # Entry is recorded before receive() so that an element passing the item straight
        # through records its entry before its exit
        target_stats = target.get_stats_collector()
        target_stats.on_entry(the_item)
        if not target.receive(the_item):
            target_stats.rollback_entry(the_item)
            logger.warning("%s refused %r although it could accept it (E_RECEIVE_REFUSED)", target.name, the_item)
            return self._wait(origin)
        origin.get_stats_collector().on_exit(the_item)
        return True

    def notify_available (self, source: Optional[Element] = None)->bool:
        non_prioritized_origins = []

        for origin in self.origins:
            if origin._output_blocks:
                continue
            if origin in self.pending_requests:
                self.pending_requests.remove(origin)
                if origin.unblock():  # The origin can return false if the output strategy does not allow the shipment
                    return True
                else:
                    self.pending_requests.append(origin)
            else:
                non_prioritized_origins.append(origin)
        # Consult the rest of inputs just in case (for instance, twice in a row to the same input queue, the second time there may not be a pending request
        for origin in non_prioritized_origins:
            if origin._output_blocks:
                continue
            if origin.unblock():
                return True
        return False

    def get_origins(self)->List[Element]:
        return self.origins

    def get_destinations(self)->List[Element]:
        return self.destinations
