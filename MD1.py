from PyFlow import *
from scipy import stats
import sys

def main():
    
    clock = SimClock.create_simulation()

    arrival_distribution = stats.expon(scale=5)

    source = InterArrivalSource("Source", clock, arrival_distribution)
    buffer = ItemQueue(100000, "Queue", clock)
    sink = Sink("Sink", clock) 

    multiassembler_distribution = stats.uniform(loc=2,scale=0)
    procesor = MultiServer(1, [multiassembler_distribution], "Procesador", clock)

    elements = [source, buffer, procesor, sink]

    source.connect([buffer])
    buffer.connect([procesor])
    procesor.connect([sink])

    clock.reset()

    for element in elements:
        element.start()

    with open("simulation_resultsMD1.txt", 'w') as f:
        f.write("Sample\tQueue Length\t\tAvg Waiting Time\n")

    with open("simulation_resultsMD1.txt", 'a') as f:
        
        max_sim_time = 90000000
        sim_time, index = 0, 1
        step = 90000000
        last_record = 0
    
    # today =date.today().strftime("%m-%d-%y")
    # with open(f"simulation_resultsMD1_{today}_{max_sim_time}.txt", 'w') as f:
        
        while sim_time < max_sim_time:
            clock.advance_clock(sim_time+step)
            if sink.get_stats_collector().get_var_input_value() - last_record >= 10:
                buffer_length= buffer.get_stats_collector().get_var_content_value()
                buffer_staytime = buffer.get_stats_collector().get_var_staytime_value()

                f.write(f"{index}\t{buffer_length}\t\t{buffer_staytime}\n") ##faltaría 
                
                last_record = sink.get_stats_collector().get_var_input_value()
                index += 1
            sim_time = sim_time + step

    print(f"\nSimulation Time: {clock.get_simulation_time()}")
    print(f"Items processed: {sink.get_number_items()}") 
    print(f"Buffer Avg Staytime: {buffer.get_stats_collector().get_var_staytime_average()}")
        

if __name__ == "__main__":
    main()  # Llamar al método main