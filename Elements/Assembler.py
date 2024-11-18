from collections import deque

from Items import item
from Elements import Element


class Assembler(Element, item):
    def __init__(self, types, demand, capacity, name, state):
        super().__init__(name, state)
        self.types=types
        self.demand=demand
        self.capacity=capacity

        self.loading_items=deque(maxlen=capacity)
        self.current_items=0

    def get_types(self):
        return self.types
    
    def get_demand(self):
        return self.demand
    
    def get_capacity(self):
        return self.capacity
    
    def start(self):
        self.loading_items.clear()

    def retreive(self):
        raise NotImplementedError ("Not supported yet. ")
    
    def notify_request(self):
        raise NotImplementedError ("Not supported yet. ")
    
    def receive(self, the_item):
        type_index=-1

        for i in range(len(self.types)):
            if self.types[i]==0:
                type_index=i
                break
            elif the_item.get_type()==self.types[i]:
                type_index=i
                break

        if type_index<0:
            return False
        
        j=0

        for content in self.loading_items:
            for i in range(len(content[type_index])):
                for i in range(len(content[type_index])):
                    content[type_index][i]=the_item

                    if j==0:
                        self.check_completed()
                        return True
                    
            j+=1

        return True
    
    def check_completed(self):
        pass

    def check_avaiability(self, the_item):
        return not(self.current_items>=self.capacity)
    
    def cancel_request(self):
        raise NotImplementedError("Not supported yet. ")
    
                    
