import sys
import os
from SimClock.SimClock import clock

from scipy import stats
import numpy as np
sys.path.append(os.path.abspath("C:/Users/Uxia/Documents/GitHub/PyFlow"))



class ProcessSim:
    
    @staticmethod
    def main():
        from Elements.ItemsQueue import ItemQueue
        from Elements.Sink import Sink
        from Elements.Link.SimpleLink import SimpleLink
        from Elements.MultiAssembler import MultiAssembler
        
        from Elements.InterArrivalSource import IntelArriveSource
        #arrival_distribution=stats.expon(scale=10)
        mean=10
        std=3
        mu=np.log(mean**2/np.sqrt(mean**2+std**2))
        sigma=np.sqrt(np.log(1+std**2/mean**2))
        arrival_distribution=stats.lognorm(s=sigma, scale=np.exp(mu))

        source = IntelArriveSource("Source1", clock,arrival_distribution)
        
        elements = []
        buffer = ItemQueue(10, "Queue", clock)
        poisson_process=[stats.expon(scale=10)]
        sink = Sink("Sink", clock)

        assembler_requirements = [1]
        multi_assembler = MultiAssembler(
            1, assembler_requirements, poisson_process, "Assembler", clock, batch_mode=False
        )


        elements.append(source)   
        elements.append(buffer)
        elements.append(multi_assembler)
        elements.append(sink)

        SimpleLink.create_link(source,buffer)
        SimpleLink.create_link(buffer,multi_assembler.get_input(0))
        SimpleLink.create_link(multi_assembler,sink)

        #Inicializacion
        clock.reset()
        for element in elements:
            element.start()

        #Ejecutar Simulacion
        clock.advance_clock(1000) ##Directamente así

        print(f"Simulation Time: {clock.get_simulation_time()}")
        print(f"Completed items: {sink.get_number_items()}")
        sys.exit(0)  # Terminar el programa

if __name__ == "__main__":
    ProcessSim.main()  # Llamar al método main
