import time
import unittest
from PyFlow import *
from scipy import stats
import sys

def main():
    print(f"\n - Test ScheduleSource:")

    clock = SimClock.get_instance()

    model_item = Item(0, labels={"Test": "Label1"}, model_item=True)
    source1 = ScheduleSource("Source", clock, "model_scheduleSource.csv", model_item)
    # source1 = ScheduleSource("Source", clock, "test_scheduleSource.data", model_item)
    buffer1 = ItemsQueue(1, "Queue", clock)

    # process_distribution = stats.uniform(loc=4,scale=0)
    process_distribution = stats.expon(scale=4)
    processor = MultiServer(1, process_distribution, "Process", clock)
    sink = Sink("Sink", clock) 

    source1.connect([buffer1])
    buffer1.connect([processor])
    processor.connect([sink])

    clock.initialize()

    last_time, elapsed_time = time.time(), 0
        
    max_sim_time = 100
    sim_time = 0
    step = 10
    
    while sim_time < max_sim_time:
        clock.advance_clock(sim_time+step)        
        sim_time = sim_time + step
        
        if time.time() - last_time > 20:
            elapsed_time+= time.time() - last_time
            last_time = time.time()
            print(f"Progress: {round(sim_time/max_sim_time*100,2)}%")
            print(f"Elapsed Time: {elapsed_time}s")


    print(f"\nSimulation Time: {clock.get_simulation_time()}")
    print(f"Items processed: {sink.get_stats_collector().get_var_input_value()}") 
    print(f"Items processed: {processor.get_stats_collector().get_var_output_value()}") 

    print(f"Buffer Avg Staytime: {buffer1.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer Avg Queue Length: {buffer1.get_stats_collector().get_var_content_average()}")

if __name__ == "__main__":
    main()