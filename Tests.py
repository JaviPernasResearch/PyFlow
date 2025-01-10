import time
from PyFlow import *
from scipy import stats
import sys

def main_multiAssembler():
    
    clock = SimClock.get_instance()

    arrival_distribution = stats.uniform(loc=4,scale=0)

    source1 = InterArrivalSource("Source", clock, arrival_distribution)
    source2 = InterArrivalSource("Source", clock, arrival_distribution)
    buffer1 = ItemQueue(100, "Queue", clock)
    buffer2 = ItemQueue(100, "Queue", clock)
    sink = Sink("Sink", clock) 

    process_distribution = stats.uniform(loc=4,scale=0)
    # process_distribution = stats.expon(scale=4)
    MAssembler = MultiAssembler(1, [1,1], process_distribution, "MultiAssembler", clock)

    elements = [source1, source2, buffer1, buffer2, MAssembler, sink]

    source1.connect([buffer1])
    source2.connect([buffer2])
    buffer1.connect([MAssembler.get_component_input(0)])
    buffer2.connect([MAssembler.get_component_input(1)])
    MAssembler.connect([sink])

    clock.reset()

    for element in elements:
        element.start()

    last_time, elapsed_time = time.time(), 0

    with open("simulation_resultsMD1.txt", 'w') as f:
        f.write("Sample\tQueue Length\t\tAvg Waiting Time\n")
        
    max_sim_time = 100
    sim_time = 0
    step = 10
    last_record = 0
    
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

def main_combiner():
    
    clock = SimClock.get_instance()

    arrival_distribution = stats.uniform(loc=2,scale=0)

    source1 = InterArrivalSource("Source", clock, arrival_distribution)
    source2 = InterArrivalSource("Source", clock, arrival_distribution)
    buffer1 = ItemQueue(100, "Queue", clock)
    buffer2 = ItemQueue(100, "Queue", clock)
    sink = Sink("Sink", clock) 

    process_distribution = stats.uniform(loc=4,scale=0)
    # process_distribution = stats.expon(scale=4)
    combiner = Combiner([2], process_distribution, "Combiner", clock)

    elements = [source1, source2, buffer1, buffer2, combiner, sink]

    source1.connect([buffer1])
    source2.connect([buffer2])
    buffer1.connect([combiner])
    buffer2.connect([combiner.get_component_input(0)])
    combiner.connect([sink])

    clock.reset()

    for element in elements:
        element.start()

    last_time, elapsed_time = time.time(), 0

    with open("simulation_resultsMD1.txt", 'w') as f:
        f.write("Sample\tQueue Length\t\tAvg Waiting Time\n")
        
    max_sim_time = 100
    sim_time = 0
    step = 10
    last_record = 0
    
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
    print(f"Items processed: {combiner.get_stats_collector().get_var_output_value()}") 

    print(f"Buffer Avg Staytime: {buffer1.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer Avg Queue Length: {buffer1.get_stats_collector().get_var_content_average()}")


def main_scheduleSource():
    
    clock = SimClock.get_instance()

    model_item = Item(0, labels={"Test": "Label1"}, model_item=True)
    source1 = ScheduleSource("Source", clock, "schedule_data.csv", model_item)
    buffer1 = ItemQueue(1, "Queue", clock)
    

    # process_distribution = stats.uniform(loc=4,scale=0)
    process_distribution = stats.expon(scale=4)
    processor = MultiServer(1, process_distribution, "Process", clock)
    sink = Sink("Sink", clock) 
    elements = [source1, buffer1, processor, sink] #this shoudl be automatic.

    source1.connect([buffer1])
    buffer1.connect([processor])
    processor.connect([sink])

    clock.reset()

    for element in elements:
        element.start()

    last_time, elapsed_time = time.time(), 0

    with open("simulation_resultsMD1.txt", 'w') as f:
        f.write("Sample\tQueue Length\t\tAvg Waiting Time\n")
        
    max_sim_time = 100
    sim_time = 0
    step = 10
    last_record = 0
    
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
    print(f"Items processed: {processor.get_stats_collector().get_var_output_value()}") 

    print(f"Buffer Avg Staytime: {buffer1.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer Avg Queue Length: {buffer1.get_stats_collector().get_var_content_average()}")

def main_scheduleSource_labelBasedProcessTime():
    
    clock = SimClock.get_instance()

    model_item = Item(0, labels={"PT": "5"}, model_item=True) # PT refers to process time.
    source1 = ScheduleSource("Source", clock, "schedule_data.csv", model_item)
    buffer1 = ItemQueue(1, "Queue", clock)
    

    process_distribution = "PT"
    # process_distribution = stats.expon(scale=4)
    processor = MultiServer(1, process_distribution, "Process", clock)
    sink = Sink("Sink", clock) 
    elements = [source1, buffer1, processor, sink] #this shoudl be automatic.

    source1.connect([buffer1])
    buffer1.connect([processor])
    processor.connect([sink])

    clock.reset()

    for element in elements:
        element.start()

    last_time, elapsed_time = time.time(), 0

    with open("simulation_resultsMD1.txt", 'w') as f:
        f.write("Sample\tQueue Length\t\tAvg Waiting Time\n")
        
    max_sim_time = 100
    sim_time = 0
    step = 10
    last_record = 0
    
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
    print(f"Items processed: {processor.get_stats_collector().get_var_output_value()}") 

    print(f"Buffer Avg Staytime: {buffer1.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer Avg Queue Length: {buffer1.get_stats_collector().get_var_content_average()}")
        
def main_scheduleSource_combiner():
    
    clock = SimClock.get_instance()

    chapa_item = Item(0, name = "Chapa", model_item=True)
    refuerzo_item = Item(0, name="previa", model_item=True)
    source_chapas = ScheduleSource("Source", clock, "schedule_chapas.data", chapa_item)
    source_refuerzos = ScheduleSource("Source", clock, "schedule_refuerzos.data", refuerzo_item)
    buffer_chapas = ItemQueue(1000, "Queue", clock)
    buffer_refuerzos = ItemQueue(1000, "Queue", clock)
    

    process_distribution = stats.uniform(loc=5,scale=0)
    # process_distribution = stats.expon(scale=4)
    welding = Combiner([1], process_distribution, "Soldadura", clock, pull_mode=SingleLabelStrategy("Previa_ID"), 
                       update_requirements = True, update_labels=["nRefuerzos"])
    sink = Sink("Sink", clock) 
    elements = [source_chapas, source_refuerzos, buffer_chapas, buffer_refuerzos, welding, sink] #this should be automatic.

    source_chapas.connect([buffer_chapas])
    source_refuerzos.connect([buffer_refuerzos])
    buffer_chapas.connect([welding])
    buffer_refuerzos.connect([welding.get_component_input(0)])
    welding.connect([sink])

    clock.reset()

    for element in elements:
        element.start()

    last_time, elapsed_time = time.time(), 0

    with open("simulation_resultsMD1.txt", 'w') as f:
        f.write("Sample\tQueue Length\t\tAvg Waiting Time\n")
        
    max_sim_time = 100
    sim_time = 0
    step = 10
    last_record = 0
    
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
    print(f"Items processed: {welding.get_stats_collector().get_var_output_value()}") 

    print(f"Buffer Avg Staytime: {buffer_refuerzos.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer Avg Queue Length: {buffer_refuerzos.get_stats_collector().get_var_content_average()}")

if __name__ == "__main__":
    main_combiner()  # Llamar al método main