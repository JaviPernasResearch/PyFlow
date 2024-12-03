from SimClock.SimClock import clock
import sys
from scipy import stats

class ProcessSim: 

    @staticmethod
    def main():
        from Elements.ItemsQueue import ItemQueue
        from Elements.MultiAssembler import MultiAssembler
        from Elements.Sink import Sink
        from Elements.Link.SimpleLink import SimpleLink

        elements = []

        #from Elements.InfinitySource import InfiniteSource
        # source1 = InfiniteSource("Source1", clock)
        # source2 = InfiniteSource("Source2", clock)

        from Elements.InterArrivalSource import IntelArriveSource
        arrival_distribution1=stats.expon(scale=10)
        arrival_distribution2=stats.expon(scale=15)
        source1 = IntelArriveSource("Source1", clock,arrival_distribution1)
        source2 = IntelArriveSource("Source2", clock,arrival_distribution2)
        
        # from Elements.ScheduleSource import ScheduleSource
        # source1=ScheduleSource("Source1", clock, "schedule_data.xlsx")
        # source2=ScheduleSource("Source2", clock, "schedule_data.xlsx")

        buffer1 = ItemQueue(10, "Queue1", clock)
        buffer2 = ItemQueue(10, "Queue2", clock)

        #poisson_process=[stats.uniform(loc=10, scale=0)]
        poisson_process=[stats.expon(scale=10)]

        sink = Sink("Sink", clock)

        assembler_requirements = [2, 1]  
        
        multi_assembler = MultiAssembler(
            1, assembler_requirements, poisson_process, "Assembler", clock, batch_mode=False
        )


        elements.append(source1)
        elements.append(buffer1)
        elements.append(source2)
        elements.append(buffer2)
        elements.append(multi_assembler)
        elements.append(sink)
    
        SimpleLink.create_link(source1, buffer1)
        SimpleLink.create_link(buffer1, multi_assembler.get_input(0))
        SimpleLink.create_link(source2, buffer2)
        SimpleLink.create_link(buffer2, multi_assembler.get_input(1))
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
