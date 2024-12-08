from SimClock.SimClock import clock
from scipy import stats
import sys

class ProcessSim:
    
    @staticmethod
    def main():
        from Elements.ItemsQueue import ItemQueue
        from Elements.Sink import Sink
        from Elements.InterArrivalSource import IntelArriveSource
        from Elements.MultiAssembler import MultiAssembler
        from Elements.Link.SimpleLink import SimpleLink  
        
        arrival_distribution = stats.expon(scale=4)
        
        source = IntelArriveSource("Source", clock, arrival_distribution)
        
        buffer = ItemQueue(10, "Queue", clock)
        sink = Sink("Sink", clock) 
        
        multiassembler_distribution = stats.expon(scale=2)
        
        multi_assembler = MultiAssembler(
            1, [1], [multiassembler_distribution], "Assembler", clock, batch_mode=False
        )

        elements = [source, buffer, multi_assembler, sink]

        SimpleLink.create_link(source, buffer)
        SimpleLink.create_link(buffer, multi_assembler.get_input(0))
        SimpleLink.create_link(multi_assembler, sink)

        # Inicialización del reloj y los elementos
        clock.reset()
        
        for element in elements:
            element.start()

        clock.advance_clock(100000000)
        with open("simulation_resultsMM110.txt", 'w') as f:
            f.write("Sample\tQueue Length\tAvg Waiting Time\n")
            for index, (length, avg_time) in enumerate(zip(buffer.get_queue_length_data(), buffer.get_average_waiting_time_data())):
                f.write(f"{index + 1}\t{length}\t\t{avg_time}\n")

        print(f"Simulation Time: {clock.get_simulation_time()}")
        print(f"Items processed: {sink.get_number_items()}")  
        

if __name__ == "__main__":
    ProcessSim.main()  # Llamar al método main