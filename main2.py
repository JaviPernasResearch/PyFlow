from SimClock.SimClock import clock
import sys
from scipy import stats

class ProcessSim: 

    @staticmethod
    def main():
        from Elements.InfinitySource import InfiniteSource
        from Elements.ItemsQueue import ItemQueue
        #from Elements.ConstrainedInput import ConstrainedInput
        from Elements.MultiAssembler import MultiAssembler
        from Elements.Sink import Sink
        from Elements.Link.SimpleLink import SimpleLink
        #from random_processes.PoissonProcess import PoissonProcess   
        #from random_processes.ConstantDouble import ConstantDouble

        elements = []

        source1 = InfiniteSource("Source1", clock)
        source2 = InfiniteSource("Source2", clock)

        buffer1 = ItemQueue(10, "Queue1", clock)
        buffer2 = ItemQueue(10, "Queue2", clock)

        #poisson_process = PoissonProcess(clock, 5)
        #poisson_process = ConstantDouble(clock, 10) 
        #poisson_process=[stats.uniform(loc=10, scale=0) ]
        poisson_process=[stats.expon(scale=10)]

        sink = Sink("Sink", clock)


        # constrained_input1 = ConstrainedInput(5, None, 0, "Input1", clock)  
        # constrained_input2 = ConstrainedInput(5, None, 1, "Input2", clock)  

        assembler_requirements = [2, 1]  
        
        multi_assembler = MultiAssembler(
            1, assembler_requirements, poisson_process, "Assembler", clock, batch_mode=False
        )

        # constrained_input1.aListener = multi_assembler
        # constrained_input2.aListener = multi_assembler

        elements.append(source1)
        elements.append(buffer1)
        elements.append(source2)
        elements.append(buffer2)
        # elements.append(constrained_input1)
        # elements.append(constrained_input2)
        elements.append(multi_assembler)
        elements.append(sink)
    
        SimpleLink.create_link(source1, buffer1)
        SimpleLink.create_link(buffer1, multi_assembler.get_input(0))
        SimpleLink.create_link(source2, buffer2)
        SimpleLink.create_link(buffer2, multi_assembler.get_input(1))
        # SimpleLink.create_link(buffer2, constrained_input2)
        SimpleLink.create_link(multi_assembler, sink)

        # Inicialización
        clock.reset()
        for element in elements:
            element.start()

        # Ejecutar simulación
        clock.advance_clock(1000)

        # Resultados finales
        print(f"Simulation Time: {clock.get_simulation_time()}")
        print(f"Completed items: {sink.get_number_items()}")
        sys.exit(0)  # Terminar el programa

if __name__ == "__main__":
    ProcessSim.main()
