import time
from PyFlow import *
from scipy import stats
import sys

def test_MD1():
    print(f"\n - Test MD1:")

    #First we create the clock
    clock = SimClock.get_instance()

    arrival_distribution = stats.expon(scale=5)

    source = InterArrivalSource("Source", clock, arrival_distribution)
    buffer = ItemsQueue(100000, "Queue", clock)
    sink = Sink("Sink", clock) 

    process_distribution = stats.uniform(loc=2,scale=0)
    procesor = MultiServer(1, process_distribution, "Procesador", clock)

    source.connect([buffer])
    buffer.connect([procesor])
    procesor.connect([sink])

    #After connecting the elements, we must initialize the simulation
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

    print(f"Buffer Avg Staytime: {buffer.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer Avg Queue Length: {buffer.get_stats_collector().get_var_content_average()}")

def test_MM1():
    print(f"\n - Test MM1:")

    #First we create the clock
    clock = SimClock.get_instance()
    
    arrival_distribution =  stats.expon(scale=2)

    source = InterArrivalSource("Source", clock, arrival_distribution)
    buffer = ItemsQueue(100, "Queue", clock)
    sink = Sink("Sink", clock) 

    process_distribution = stats.expon(scale=2)
    procesor = MultiServer(1, process_distribution, "Procesador", clock)

    source.connect([buffer])
    buffer.connect([procesor])
    procesor.connect([sink])

    #After connecting the elements, we must initialize the simulation
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

    print(f"Buffer Avg Staytime: {buffer.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer Avg Queue Length: {buffer.get_stats_collector().get_var_content_average()}")

def test_multiAssembler():
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

def test_combiner():
    print(f"\n - Test Combiner:")

    clock = SimClock.get_instance()

    arrival_distribution = stats.uniform(loc=2,scale=0)

    source1 = InterArrivalSource("Source", clock, arrival_distribution)
    source2 = InterArrivalSource("Source", clock, arrival_distribution)
    buffer1 = ItemsQueue(100, "Queue", clock)
    buffer2 = ItemsQueue(100, "Queue", clock)
    sink = Sink("Sink", clock) 

    process_distribution = stats.uniform(loc=4,scale=0)
    # process_distribution = stats.expon(scale=4)
    combiner = Combiner([2], process_distribution, "Combiner", clock)

    source1.connect([buffer1])
    source2.connect([buffer2])
    buffer1.connect([combiner])
    buffer2.connect([combiner.get_component_input(0)])
    combiner.connect([sink])

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
    print(f"Items processed: {combiner.get_stats_collector().get_var_output_value()}") 

    print(f"Buffer Avg Staytime: {buffer1.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer Avg Queue Length: {buffer1.get_stats_collector().get_var_content_average()}")

def test_scheduleSource():
    print(f"\n - Test ScheduleSource:")

    clock = SimClock.get_instance()

    model_item = Item(0, labels={"Test": "Label1"}, model_item=True)
    source1 = ScheduleSource("Source", clock, "test_scheduleSource.csv", model_item)
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

def test_labelBasedPT():
    print(f"\n - Test Label-based PT:")

    clock = SimClock.get_instance()

    model_item = Item(0, labels={"PT": "5"}, model_item=True) # PT refers to process time.
    source1 = ScheduleSource("Source", clock, "test_scheduleSource.xlsx", model_item)
    buffer1 = ItemsQueue(1, "Queue", clock)
    
    processor = MultiServer(1, "PT", "Process", clock)
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
        
def test_combiner_basedOnLabel():
    
    print(f"\n - Test Label-based Combiner List:")
 

    clock = SimClock.get_instance()

    chapa_item = Item(0, name = "Chapa", model_item=True)
    refuerzo_item = Item(0, name="previa", model_item=True)
    source_chapas = ScheduleSource("Source", clock, "test_combiner_basedOnLabel_chapas.data", chapa_item)
    source_refuerzos = ScheduleSource("Source", clock, "test_combiner_basedOnLabel_refuerzos.data", refuerzo_item)
    buffer_chapas = ItemsQueue(1000, "Queue", clock)
    buffer_refuerzos = ItemsQueue(1000, "Queue", clock)
    

    process_distribution = stats.uniform(loc=5,scale=0)
    # process_distribution = stats.expon(scale=4)
    welding = Combiner([1], process_distribution, "Soldadura", clock, pull_mode=SingleLabelStrategy("Previa_ID"), 
                       update_requirements = True, update_labels=["nRefuerzos"])
    sink = Sink("Sink", clock) 

    source_chapas.connect([buffer_chapas])
    source_refuerzos.connect([buffer_refuerzos])
    buffer_chapas.connect([welding])
    buffer_refuerzos.connect([welding.get_component_input(0)])
    welding.connect([sink])

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
    print(f"Items processed: {welding.get_stats_collector().get_var_output_value()}") 

    print(f"Buffer Avg Staytime: {buffer_refuerzos.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer Avg Queue Length: {buffer_refuerzos.get_stats_collector().get_var_content_average()}")

def test_MultipleLink_21():
    print(f"\n - Test Multiple Link 2-1:")

    #First we create the clock
    clock = SimClock.get_instance()

    arrival_distribution = stats.uniform(loc=2, scale = 0)

    source1 = InterArrivalSource("Source", clock, arrival_distribution)
    source2 = InterArrivalSource("Source", clock, arrival_distribution)
    buffer = ItemsQueue(100000, "Queue", clock)
    sink = Sink("Sink", clock) 

    process_distribution = stats.uniform(loc=2,scale=0)
    procesor = MultiServer(1, process_distribution, "Procesador", clock)

    # There are two ways of making multiple connections
    # Way 1: Using the static connect_multiple method
    Element.connect_multiple([source1, source2], [buffer])
    # Way 2: Using the connect method of the element (uncomment the following lines and comment the previous one)
    # source1.connect([buffer])
    # source2.connect([buffer])
    
    buffer.connect([procesor])
    procesor.connect([sink])

    #After connecting the elements, we must initialize the simulation
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

    print(f"Buffer Avg Staytime: {buffer.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer Avg Queue Length: {buffer.get_stats_collector().get_var_content_average()}")

def test_MultipleLink_12():
    print(f"\n - Test Multiple Link 1-2:")

    #First we create the clock
    clock = SimClock.get_instance()

    arrival_distribution = stats.uniform(loc=2, scale = 0)

    source1 = InterArrivalSource("Source", clock, arrival_distribution)
    buffer1 = ItemsQueue(3, "Queue1", clock)
    buffer2 = ItemsQueue(3, "Queue2", clock)
    sink = Sink("Sink", clock) 

    process_distribution = stats.uniform(loc=2,scale=0)
    procesor1 = MultiServer(1, process_distribution, "Procesador1", clock)
    procesor2 = MultiServer(1, process_distribution, "Procesador2", clock)

    # Element.connect_multiple([source1], [buffer1, buffer2])
    source1.connect([buffer1])
    source1.connect([buffer2])
    buffer1.connect([procesor1])
    buffer2.connect([procesor2])
    procesor1.connect([sink])
    procesor2.connect([sink])

    #After connecting the elements, we must initialize the simulation
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

    print(f"Buffer1 Avg Staytime: {buffer1.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer1 Avg Queue Length: {buffer1.get_stats_collector().get_var_content_average()}")
    print(f"Buffer1 Output: {buffer1.get_stats_collector().get_var_output_value()}")
    print(f"Buffer2 Avg Staytime: {buffer2.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer2 Avg Queue Length: {buffer2.get_stats_collector().get_var_content_average()}")
    print(f"Buffer2 Output: {buffer2.get_stats_collector().get_var_output_value()}")

def test_MultipleLink_22():
    print(f"\n - Test Multiple Link 2-2:")

    #First we create the clock
    clock = SimClock.get_instance()

    arrival_distribution = stats.uniform(loc=2, scale = 0)

    # source1 = InterArrivalSource("Source1", clock, arrival_distribution)
    # source2 = InterArrivalSource("Source2", clock, arrival_distribution)
    source1 = InfiniteSource(name= "Source1", clock=clock)
    source2 = InfiniteSource(name= "Source2", clock=clock)

    buffer1 = ItemsQueue(3, "Queue1", clock)
    buffer2 = ItemsQueue(3, "Queue2", clock)
    sink = Sink("Sink", clock) 

    process_distribution1 = stats.uniform(loc=20,scale=0)
    process_distribution2 = stats.uniform(loc=10,scale=0)
    procesor1 = MultiServer(1, process_distribution1, "Procesador1", clock)
    procesor2 = MultiServer(1, process_distribution2, "Procesador2", clock)

    # Element.connect_multiple([source1, source2], [buffer1, buffer2])
    source1.connect([buffer1, buffer2])
    source2.connect([buffer2, buffer1])
    buffer1.connect([procesor1])
    buffer2.connect([procesor2])
    procesor1.connect([sink])
    procesor2.connect([sink])

    #After connecting the elements, we must initialize the simulation
    clock.initialize()

    last_time, elapsed_time = time.time(), 0
        
    max_sim_time = 100
    sim_time = 0
    step = 1
    
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

    print(f"Buffer1 Avg Staytime: {buffer1.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer1 Avg Queue Length: {buffer1.get_stats_collector().get_var_content_average()}")
    print(f"Buffer1 Output: {buffer1.get_stats_collector().get_var_output_value()}")
    print(f"Buffer2 Avg Staytime: {buffer2.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer2 Avg Queue Length: {buffer2.get_stats_collector().get_var_content_average()}")
    print(f"Buffer2 Output: {buffer2.get_stats_collector().get_var_output_value()}")

if __name__ == "__main__":
    test_MD1()
    test_MM1()
    test_multiAssembler()  
    test_combiner() 
    test_scheduleSource()
    test_labelBasedPT()
    test_combiner_basedOnLabel()  
    test_MultipleLink_21()  
    test_MultipleLink_12()  
    test_MultipleLink_22()  