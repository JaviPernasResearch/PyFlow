import time
from PyFlow import *
from scipy import stats
import sys

       
def main():
    
    clock = SimClock.get_instance()

    chapa_item = Item(0, name = "Chapa", model_item=True)
    refuerzo_item = Item(0, name="previa", model_item=True)
    source_chapas = ScheduleSource("SourceChapas", clock, "CEMI_chapas.xlsx", chapa_item)
    source_refuerzos = ScheduleSource("SourceRefuerzos", clock, "CEMI_refuerzos.xlsx", refuerzo_item)
    buffer_chapas = ItemsQueue(1000, "QueueChapas", clock)
    buffer_refuerzos = ItemsQueue(1000, "QueueRefuerzos", clock)
    

    process_distribution = stats.uniform(loc=5,scale=0)
    # process_distribution = stats.expon(scale=4)
    welding = Combiner([1], "tSoldadura", "Welding", clock, pull_mode=SingleLabelStrategy("Referencia"), 
                       update_requirements = True, update_labels=["nRefuerzos"])
    sink = Sink("Sink", clock) 
    # elements = [source_chapas, source_refuerzos, buffer_chapas, buffer_refuerzos, welding, sink] #this should be automatic.

    source_chapas.connect([buffer_chapas])
    source_refuerzos.connect([buffer_refuerzos])
    buffer_chapas.connect([welding])
    buffer_refuerzos.connect([welding.get_component_input(0)])
    welding.connect([sink])

    clock.initialize()

    last_time, elapsed_time = time.time(), 0
        
    max_sim_time = 100000
    sim_time = 0
    step = 10
    last_record = 0
    
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

    print(f"Buffer Avg Staytime: {buffer_refuerzos.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer Avg Queue Length: {buffer_refuerzos.get_stats_collector().get_var_content_max()}")

if __name__ == "__main__":
    main()  # Llamar al método main