from collections import deque
from typing import List, Deque

from ..Elements.element import Element
from ..SimClock.simClock import SimClock
from ..Items.item import Item
from .link import Link


class MultipleLink (Link):
    def __init__(self, inputs:List[Element], outputs:List[Element], clock:SimClock): # type: ignore
        self.inputs:List[Element]=inputs
        self.outputs:List[Element]=outputs
        self.clock:SimClock=clock
        self.pending_request:Deque[int]=deque()

    def send(self, the_item:Item, origin:Element)->bool:
        index_origin=0
        index_destination=0

        for i, input_element in enumerate(self.inputs): 
            if origin==input_element:
                index_origin=i
                break

        index_destination=self.find_output(the_item)

        if index_destination<0:
            for output in self.outputs:
                output.receive(the_item)
            self.pending_request.append(index_origin)
            return False
        else:
            self.outputs[index_destination].receive(the_item)
            return True
    

    def NotifyAvaliable (self, destination:Element)->bool:
        if len(self.pending_request)>0:
            input_index=self.pending_request.popleft()

            the_item:Item=self.inputs[input_index].retrieve()

            if the_item is None:
                return False
            
            destination.receive(the_item)

            for output in self.outputs:
                if output != destination:
                    output.cancel_request()


            self.inputs [input_index].notify_request()
            return True
        else:
            return True
        
    def find_output(self, the_item:Item)->int:
        for i, output in enumerate(self.outputs): 
            if output.check_availability(the_item):
                return i
        return -1

