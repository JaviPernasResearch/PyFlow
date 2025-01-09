from Elements import  InfiniteSource, ItemsQueue, MultiServer, Sink
from random_processes import PoissonProcess
from Elements.Link import SimpleLink
from SimClock.SimClock import SimClock
from Elements.Element import Element

from typing import List
import logging


class SerialLine:
    def __init__(self, seed:int):
        self.max_time:float = 0.0
        self.number_machines:int = 0
        self.server_capacity:int = 0
        self.queue_capacity:int = 0
        self.mean :float= 0.0
        self.elements :List[Element]= []
        self.the_sink:Sink = None
        self.logger=logging.getLogger(__name__)
        self.clock=SimClock
        self,seed=seed

    def setup(self, max_time:float, number_machines:int, server_capacity:int, mean:float)->None:
        self.max_time = max_time
        self.number_machines = number_machines
        self.server_capacity = server_capacity
        self.mean = mean

    def load_scenario(self, scenario:str)->None:
        fields = scenario.split("\t")
        
        self.max_time = float(fields[0])
        self.number_machines = int(fields[1])
        self.server_capacity = int(fields[2])
        self.queue_capacity = int(fields[3])
        self.mean = float(fields[4])

    def generate_elements(self):
        poisson_process = PoissonProcess(self.clock, self.mean)
        times = [poisson_process for _ in range(self.server_capacity) ]

        self.elements = []
        
        # Añadir InfiniteSource
        self.elements.append(InfiniteSource("Source", self.clock))
        
        # Añadir WorkStation y ItemsQueue
        for i in range(1, self.number_machines + 1):
            self.elements.append(MultiServer(times, f"M{i}", self.clock))
            if i < self.number_machines:
                self.elements.append(ItemsQueue(self.queue_capacity, f"Q{i}", self.clock))

        self.the_sink = Sink("Sink", self.clock)
        self.elements.append(self.the_sink)

        # Crear enlaces simples entre los elementos
        for i in range(len(self.elements) - 1):
            SimpleLink.create_link(self.elements[i], self.elements[i + 1])

    def start(self)->None:
        self.clock.reset()
        for element in self.elements():
            element.start()

    def finish(self)->None:
        print(f"Completed items: {self.the_sink.get_number_items()}")

    def run(self):
        self.start()
        
        while (self.clock.get_simulation_time() <= self.max_time) and self.clock.advance_clock.step(1000):
            pass  # Ciclo vacío
        
        self.finish()

    def report_summary(self)->str:
        summary = f"OUTPUT\t{self.the_sink.get_number_items()}"
        return summary
