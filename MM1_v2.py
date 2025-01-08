from SimClock.SimClock import clock
from scipy import stats
import sys
from datetime import date

class ProcessSim:
    
    @staticmethod
    def main():
        from Elements.ItemsQueue import ItemQueue
        from Elements.Sink import Sink
        from Elements.InterArrivalSource import IntelArriveSource
        from Elements.MultiServer import MultiServer
        from Elements.Link.SimpleLink import SimpleLink  
    
        arrival_distribution =  stats.expon(scale=2)
    
        source = IntelArriveSource("Source", clock, arrival_distribution)
        buffer = ItemQueue(10000000, "Queue", clock)
        sink = Sink("Sink", clock) 
    
        multiassembler_distribution = stats.expon(scale=2)
        procesor = MultiServer(1, [multiassembler_distribution], "Procesador", clock)

        elements = [source, buffer, procesor, sink]

        SimpleLink.create_link(source, buffer)
        SimpleLink.create_link(buffer, procesor)
        SimpleLink.create_link(procesor, sink)

        clock.reset()
    
        for element in elements:
            element.start()

        with open("simulation_resultsMD1.txt", 'w') as f:
            f.write("Sample\tQueue Length\t\tAvg Waiting Time\n")
            
            max_sim_time = 10000000
            sim_time, index = 0, 1
            step = 10000000
            last_record = 0
        
        # today =date.today().strftime("%m-%d-%y")
        # with open(f"simulation_resultsMD1_{today}_{max_sim_time}.txt", 'w') as f:
            
            while sim_time < max_sim_time:
                if not clock.advance_clock(sim_time+step):
                    print("ERROR")
                if sink.get_number_items() - last_record >= 1000:
                    # f.write(f"{index}\t{buffer.get_queue_length_data()}\t\t{buffer.get_last_time_waiting_time_data()}\n") ##faltaría 
                    last_record = sink.get_number_items()
                    index += 1
                sim_time = sim_time + step

        print(f"\nSimulation Time: {clock.get_simulation_time()}")
        print(f"Items processed: {sink.get_number_items()}") 
        

if __name__ == "__main__":
    ProcessSim.main()  # Llamar al método main