import time
from PyFlow import *
from scipy import stats
import sys

def main():
    
    #First we create the clock
    clock = SimClock.get_instance()

    arrival_distribution = stats.expon(scale=5)

    source = InterArrivalSource("Source", clock, arrival_distribution)
    buffer = ItemQueue(100000, "Queue", clock)
    sink = Sink("Sink", clock) 

    process_distribution = stats.uniform(loc=2,scale=0)
    procesor = MultiServer(1, process_distribution, "Procesador", clock)

    source.connect([buffer])
    buffer.connect([procesor])
    procesor.connect([sink])

    #After connecting the elements, we must initialize the simulation
    clock.initialize()

    last_time, elapsed_time = time.time(), 0

    with open("simulation_resultsMD1.txt", 'w') as f:
        f.write("Sample\tQueue Length\t\tAvg Waiting Time\n")
        
    max_sim_time = 90000000
    sim_time = 0
    step = 10
    last_record = 0
    
    while sim_time < max_sim_time:
        clock.advance_clock(sim_time+step)
        if sink.get_stats_collector().get_var_input_value() - last_record >= 1000:

            buffer_input= buffer.get_stats_collector().get_var_input_value()
            buffer_length= buffer.get_stats_collector().get_var_content_value()
            buffer_staytime = buffer.get_stats_collector().get_var_staytime_value()

            with open("simulation_resultsMD1.txt", 'a') as f:
                f.write(f"{buffer_input}\t{buffer_length}\t{buffer_staytime}\n") 
            
            last_record = sink.get_stats_collector().get_var_input_value()
        
        sim_time = sim_time + step
        
        if time.time() - last_time > 20:
            elapsed_time+= time.time() - last_time
            last_time = time.time()
            print(f"Progress: {round(sim_time/max_sim_time*100,2)}%")
            print(f"Elapsed Time: {elapsed_time}s")


    print(f"\nSimulation Time: {clock.get_simulation_time()}")
    print(f"Items processed: {sink.get_stats_collector().get_var_input_value()}") 

    print(f"Buffer Avg Staytime: {buffer.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer Avg Queue Length: {buffer.get_stats_collector().get_var_content_average()}")
        

if __name__ == "__main__":
    main()  # Llamar al método main