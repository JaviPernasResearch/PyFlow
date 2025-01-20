import random
import time
from PyFlow import *
from scipy import stats
import sys

       
def main():
    
    clock = SimClock.get_instance()

    # chapa_item = Item(0, name = "Chapa", model_item=True, labels={"inspeccionOn":1})
    chapa_item = Item(0, name = "Chapa", model_item=True)
    refuerzo_item = Item(0, name="previa", model_item=True)



    # Direct from the excel File
    # source_chapas = ScheduleSource("SourceChapas", clock, file_name="CEMI_chapas.xlsx", model_item=chapa_item, sheet_name="MBOM")
    # source_refuerzos = ScheduleSource("SourceRefuerzos", clock, file_name="CEMI_refuerzos.xlsx", model_item=refuerzo_item, sheet_name="MBOM")
    
    # For optimization
    priorities  = list(range(90,0,-1)) # From the metaheuristic
    random_priorities = random.shuffle(list(range(1, 91)))
    random_inspection = [random.choice([0, 1]) for _ in range(90)]
    chapas = SeqOptTools.read_excel_to_dict("CEMI_chapas.xlsx", "MBOM")
    SeqOptTools.add_labels_to_dict(chapas, "inspeccionOn", random_inspection)
    chapas_reordered = SeqOptTools.transform_sequence(chapas, priorities)
    refuerzos = SeqOptTools.read_excel_to_dict("CEMI_refuerzos.xlsx", "MBOM")
    refuerzos_reordered = SeqOptTools.transform_sequence(refuerzos, priorities)
    # Sources read from the dict
    source_chapas = ScheduleSource("SourceChapas", clock, model_item=chapa_item, data_dict= chapas_reordered)
    source_refuerzos = ScheduleSource("SourceRefuerzos", clock, model_item=refuerzo_item, data_dict= refuerzos_reordered)
    buffer_chapas = ItemsQueue(1000, "QueueChapas", clock)
    buffer_refuerzos = ItemsQueue(1000, "QueueRefuerzos", clock)
    

    process_distribution = stats.uniform(loc=5,scale=0)
    # process_distribution = stats.expon(scale=4)
    welding = Combiner([1], "item.get_label_value('tSoldadura') + item.get_label_value('tInspeccion')* item.get_label_value('inspeccionOn')", "Welding", clock, pull_mode=SingleLabelStrategy("Referencia"), 
                       update_requirements = True, update_labels=["nRefuerzos"])
    # inspection = MultiServer(1, "tInspeccion", "Inspection", clock)
    sink = Sink("Sink", clock) 
    # elements = [source_chapas, source_refuerzos, buffer_chapas, buffer_refuerzos, welding, sink] #this should be automatic.
    
    source_chapas.connect([buffer_chapas])
    source_refuerzos.connect([buffer_refuerzos])
    buffer_chapas.connect([welding])
    buffer_refuerzos.connect([welding.get_component_input(0)])
    # Element.connect_multiple([welding],[sink, inspection], strategy=LabelBasedStrategy("inspeccionOn"))
    # inspection.connect([sink])
    welding.connect([sink])

    clock.initialize()

    last_time, elapsed_time = time.time(), 0
        
    max_sim_time = 100000
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

    print(f"Buffer Avg Staytime: {buffer_refuerzos.get_stats_collector().get_var_staytime_average()}")
    print(f"Buffer Avg Queue Length: {buffer_refuerzos.get_stats_collector().get_var_content_max()}")

if __name__ == "__main__":
    main()  # Llamar al método main