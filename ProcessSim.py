#import logging
import sys
import os
from SimClock.SimClock import clock

#logging.basicConfig(level=logging.INFO)
# logger=logging.getLogger(__name__)

sys.path.append(os.path.abspath("C:/Users/Uxia/Documents/GitHub/PyFlow"))



class ProcessSim:
    
    def main():
        from Elements.InfinitySource import InfiniteSource
        from Elements.ItemsQueue import ItemQueue
        from random_processes.PoissonProcess import PoissonProcess
        from Elements.WorkStation import WorkStation
        from Elements.Sink import Sink
        from Elements.Link.SimpleLink import SimpleLink
        # experiment = DOE()  # Crear una nueva instancia de DOE
        
        # experiment.runs = 5  # Establecer el número de corridas a 5
        
        # experiment.load_scenarios("doe.txt")  # Cargar los escenarios desde el archivo "doe.txt"
        
        # experiment.run_experimentation()  # Ejecutar la experimentación
        
        #Generacion de elementos y links
        #clock = SimClock() Esto me da error 'module' object is no callable.
        
       # elements = []
        #source = InfiniteSource("Source", clock)
        
        #number_buffers=1
        
        """for i in range(number_buffers):
            buffer = ItemQueue(10, f"Q{i}", clock)
            poisson_process = PoissonProcess(clock, 5)
            times = [poisson_process for _ in range(1)]
            ws = WorkStation(times, f"M{i}", clock)
  
            elements.append(buffer)
            elements.append(ws)"""
        elements = []
        source = InfiniteSource("Source", clock)
        buffer = ItemQueue(10, f"Q1", clock)
        poisson_process = PoissonProcess(clock, 5)
        times = [poisson_process for _ in range(1)]
        ws = WorkStation(times, f"M1", clock)
        sink = Sink("Sink", clock)



        sink = Sink("Sink", clock)    
        elements.append(sink)
        elements.append(source)


        for i in range(len(elements) - 1):
            SimpleLink.create_link(elements[i], elements[i + 1])


        #Inicializacion
        clock.reset()
        for element in elements:
            element.start()

        #Ejecutar Simulacion
        while (clock.get_simulation_time() <= 1000) and clock.advance_clock(1000):
            pass  # Ciclo vacío

        
        print(f"Completed items: {sink.get_number_items()}")
        sys.exit(0)  # Terminar el programa

if __name__ == "__main__":
    ProcessSim.main()  # Llamar al método main
