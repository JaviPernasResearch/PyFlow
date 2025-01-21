import time
import unittest
from PyFlow import *
from scipy import stats
import sys



def main():
    print(f"\n - Test MultiAssembler:")

    clock = SimClock.get_instance()

    arrival_distribution = stats.uniform(loc=4,scale=0)

    source1 = InterArrivalSource("Source", clock, arrival_distribution)
    source2 = InterArrivalSource("Source", clock, arrival_distribution)
    buffer1 = ItemsQueue(100, "Queue", clock)
    buffer2 = ItemsQueue(100, "Queue", clock)
    sink = Sink("Sink", clock) 

    process_distribution = stats.uniform(loc=4,scale=0)
    # process_distribution = stats.expon(scale=4)
    MAssembler = MultiAssembler(1, [1,1], process_distribution, "MultiAssembler", clock)

    source1.connect([buffer1])
    source2.connect([buffer2])
    buffer1.connect([MAssembler.get_component_input(0)])
    buffer2.connect([MAssembler.get_component_input(1)])
    MAssembler.connect([sink])

    clock.initialize()

    last_time, elapsed_time = time.time(), 0

    with open("simulation_resultsMD1.txt", 'w') as f:
        f.write("Sample\tQueue Length\t\tAvg Waiting Time\n")
        
    max_sim_time = 100
    sim_time = 0
    step = 10
    
    while sim_time < max_sim_time:
        clock.advance_clock(sim_time+step)
        # if sink.get_stats_collector().get_var_input_value() - last_record >= 1000:

        #     buffer_input= buffer1.get_stats_collector().get_var_input_value()
        #     buffer_length= buffer1.get_stats_collector().get_var_content_value()
        #     buffer_staytime = buffer1.get_stats_collector().get_var_staytime_value()

        #     with open("simulation_resultsMD1.txt", 'a') as f:
        #         f.write(f"{buffer_input}\t{buffer_length}\t{buffer_staytime}\n") 
            
        #     last_record = sink.get_stats_collector().get_var_input_value()
        
        sim_time = sim_time + step
        
        if time.time() - last_time > 20:
            elapsed_time+= time.time() - last_time
            last_time = time.time()
            print(f"Progress: {round(sim_time/max_sim_time*100,2)}%")
            print(f"Elapsed Time: {elapsed_time}s")


    print(f"\nSimulation Time: {clock.get_simulation_time()}")
    print(f"Items processed: {sink.get_stats_collector().get_var_input_value()}") 
    print(f"Items processed: {MAssembler.get_stats_collector().get_var_output_value()}") 

    print(f"Buffer Avg Staytime: {buffer1.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer Avg Queue Length: {buffer1.get_stats_collector().get_var_content_average()}")


if __name__ == "__main__":
    main()  