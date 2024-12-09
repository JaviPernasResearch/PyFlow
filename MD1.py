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
        from Elements.MultiServer import MultiServer
        from Elements.Link.SimpleLink import SimpleLink  
        
        arrival_distribution = stats.expon(scale=5)
        
        source = IntelArriveSource("Source", clock, arrival_distribution)
        
        buffer = ItemQueue(100000, "Queue", clock)
        sink = Sink("Sink", clock) 
        
        multiassembler_distribution = stats.uniform(loc=2,scale=0)
        
        # multi_assembler = MultiAssembler(
        #     1, [1], [multiassembler_distribution], "Assembler", clock, batch_mode=False
        # )

        procesor = MultiServer(1, [multiassembler_distribution], "Procesador", clock)

        elements = [source, buffer, procesor, sink]

        SimpleLink.create_link(source, buffer)
        SimpleLink.create_link(buffer, procesor)
        SimpleLink.create_link(procesor, sink)

        # Inicialización del reloj y los elementos
        clock.reset()
        
        for element in elements:
            element.start()

        # clock.advance_clock(100000000)
        with open("simulation_resultsMD1.txt", 'w') as f:
            f.write("Sample\tQueue Length\tAvg Waiting Time\n")
            max_sim_time = 10000
            sim_time, index = 0, 1
            step = 0.01
            last_record = 0
            while sim_time < max_sim_time:
                clock.advance_clock(sim_time+step)
                if sink.get_number_items() - last_record >= 1000:
                    f.write(f"{index + 1}\t{buffer.get_queue_length_data()}\t\t{0}\n") ##faltaría 
                    last_record = sink.get_number_items()
                sim_time = sim_time + step
                index += 1
        # with open("simulation_resultsMD1.txt", 'w') as f:
        #     f.write("Sample\tQueue Length\tAvg Waiting Time\n")
        #     for index, (length, avg_time) in enumerate(zip(buffer.get_queue_length_data(), buffer.get_average_waiting_time_data())):
        #         f.write(f"{index + 1}\t{length}\t\t{avg_time}\n")

        print(f"Simulation Time: {clock.get_simulation_time()}")
        print(f"Items processed: {sink.get_number_items()}")  
        

if __name__ == "__main__":
    ProcessSim.main()  # Llamar al método main