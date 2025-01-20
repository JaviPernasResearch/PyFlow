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
    priorities_test1 = [
    50, 36, 74, 42, 45, 71, 51, 54, 4, 8, 35, 13, 10, 19, 9, 59, 49, 58, 23, 64, 
    76, 69, 60, 5, 21, 15, 89, 24, 30, 85, 68, 67, 34, 79, 28, 29, 80, 73, 37, 
    11, 48, 12, 22, 53, 81, 70, 47, 44, 38, 78, 90, 88, 77, 72, 57, 43, 20, 66, 
    18, 1, 6, 61, 33, 3, 65, 63, 83, 46, 55, 41, 31, 2, 62, 16, 52, 25, 84, 
    87, 75, 56, 27, 86, 82, 32, 14, 26, 17, 39, 7, 40]

    priorities_test2 = [
    33, 58, 30, 86, 85, 4, 76, 57, 2, 68, 19, 72, 80, 73, 79, 20, 10, 22, 46, 
    15, 82, 37, 56, 36, 59, 69, 14, 53, 64, 70, 32, 67, 9, 54, 55, 87, 16, 78, 
    48, 27, 89, 65, 43, 50, 7, 13, 23, 42, 8, 62, 88, 83, 38, 66, 35, 12, 26, 
    41, 49, 71, 17, 51, 44, 25, 63, 3, 84, 45, 29, 6, 90, 1, 52, 74, 18, 24, 
    5, 11, 39, 60, 34, 28, 31, 61, 40, 77, 21, 75, 81, 47
    ]

    priorities_test3 = [19, 53, 55, 54, 24, 58, 56, 70, 20, 89, 5, 32, 62, 64,
    87, 72, 82, 44, 79, 47, 48, 30, 61, 60, 63, 29, 68, 81, 25, 80, 36, 14, 74, 
    71, 39, 66, 65, 18, 6, 84, 38, 46, 35, 83, 88, 41, 49, 51, 85, 22, 50, 16, 
    28, 45, 15, 8, 78, 4, 75, 2, 11, 86, 37, 90, 40, 67, 9, 57, 26, 1, 42, 59, 31,
    34, 21, 10, 12, 77, 3, 76, 17, 13, 73, 52, 43, 23, 33, 69, 27, 7]

    priorities_test4 = [34, 62, 71, 69, 26, 47, 12, 25, 32, 66, 44, 23, 58, 29, 84,
    18, 76, 43, 22, 7, 27, 87, 89, 13, 75, 80, 74, 85, 11, 68, 73, 21, 55, 88, 40, 
    33, 56, 2, 4, 19, 17, 64, 31, 9, 50, 5, 46, 78, 35, 63, 61, 77, 54, 67, 83, 36, 
    48, 6, 16, 14, 53, 65, 81, 59, 39, 49, 79, 20, 37, 24, 30, 28, 1, 57, 70, 72, 42, 
    10, 52, 3, 15, 86, 90, 41, 82, 8, 38, 60, 45, 51]


    chapas = SeqOptTools.read_excel_to_dict("CEMI_chapas.xlsx", "MBOM")
    chapas_reordered = SeqOptTools.transform_sequence(chapas, priorities_test4)

    refuerzos = SeqOptTools.read_excel_to_dict("CEMI_refuerzos.xlsx", "MBOM")
    refuerzos_reordered = SeqOptTools.transform_sequence(refuerzos, priorities_test4)
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