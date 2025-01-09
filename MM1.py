from PyFlow import *

from scipy import stats
import sys
from datetime import date

   
def main():
    
    clock = SimClock.create_simulation()

    arrival_distribution =  stats.expon(scale=4)

    source = InterArrivalSource("Source", clock, arrival_distribution)
    buffer = ItemQueue(10000000, "Queue", clock)
    sink = Sink("Sink", clock) 

    multiassembler_distribution = stats.expon(scale=2)
    procesor = MultiServer(1, [multiassembler_distribution], "Procesador", clock)

    elements = [source, buffer, procesor, sink]

    source.connect([buffer])
    buffer.connect([procesor])
    procesor.connect([sink])

    clock.reset()

    for element in elements:
        element.start()

    with open("simulation_resultsMM1.txt", 'w') as f:
        f.write("Sample\tQueue Length\t\tAvg Waiting Time\n")
        
        max_sim_time = 10000
        sim_time, index = 0, 1
        step = 10000
        last_record = 0

        while sim_time < max_sim_time:
            if not clock.advance_clock(sim_time+step):
                print("ERROR")

            sim_time = sim_time + step

    print(f"\nSimulation Time: {clock.get_simulation_time()}")
    print(f"Items processed: {sink.get_stats_collector().get_var_input_value()}") 

    print(f"buffer avg staytime: {buffer.get_stats_collector().get_var_staytime_average()}")
        

if __name__ == "__main__":
    main()