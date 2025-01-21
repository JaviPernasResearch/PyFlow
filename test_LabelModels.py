import time
import unittest
from PyFlow import *
from scipy import stats
import sys

##PENDING REALIZATION
class TestBasicModels(unittest.TestCase):

    def setUp(self):
        # This method will run before each test to set up the environment
        SimClock._instance =  None
        self.clock = SimClock.get_instance()
        self.max_sim_time = 100
        self.step = 10
        self.sim_time = 0

# def test_labelBasedPT():
#     print(f"\n - Test Label-based PT:")

#     clock = SimClock.get_instance()

#     model_item = Item(0, labels={"PT": "5"}, model_item=True) # PT refers to process time.
#     source1 = ScheduleSource("Source", clock, "test_scheduleSource.xlsx", model_item)
#     buffer1 = ItemsQueue(1, "Queue", clock)
    
#     processor = MultiServer(1, "PT", "Process", clock)
#     sink = Sink("Sink", clock) 

#     source1.connect([buffer1])
#     buffer1.connect([processor])
#     processor.connect([sink])

#     clock.initialize()

#     last_time, elapsed_time = time.time(), 0
        
#     max_sim_time = 100
#     sim_time = 0
#     step = 10
    
#     while sim_time < max_sim_time:
#         clock.advance_clock(sim_time+step)      
#         sim_time = sim_time + step
        
#         if time.time() - last_time > 20:
#             elapsed_time+= time.time() - last_time
#             last_time = time.time()
#             print(f"Progress: {round(sim_time/max_sim_time*100,2)}%")
#             print(f"Elapsed Time: {elapsed_time}s")


#     print(f"\nSimulation Time: {clock.get_simulation_time()}")
#     print(f"Items processed: {sink.get_stats_collector().get_var_input_value()}") 
#     print(f"Items processed: {processor.get_stats_collector().get_var_output_value()}") 

#     print(f"Buffer Avg Staytime: {buffer1.get_stats_collector().get_var_staytime_average()}")
#     print(f"Buffer Avg Queue Length: {buffer1.get_stats_collector().get_var_content_average()}")
        
# def test_combiner_basedOnLabel():
    
#     print(f"\n - Test Label-based Combiner List:")
 

#     clock = SimClock.get_instance()

#     chapa_item = Item(0, name = "Chapa", model_item=True)
#     refuerzo_item = Item(0, name="previa", model_item=True)
#     source_chapas = ScheduleSource("Source", clock, "test_combiner_basedOnLabel_chapas.data", chapa_item)
#     source_refuerzos = ScheduleSource("Source", clock, "test_combiner_basedOnLabel_refuerzos.data", refuerzo_item)
#     buffer_chapas = ItemsQueue(1000, "Queue", clock)
#     buffer_refuerzos = ItemsQueue(1000, "Queue", clock)
    

#     process_distribution = stats.uniform(loc=5,scale=0)
#     process_distribution = stats.expon(scale=4)
#     welding = Combiner([1], process_distribution, "Soldadura", clock, pull_mode=SingleLabelStrategy("Previa_ID"), 
#                        update_requirements = True, update_labels=["nRefuerzos"])
#     sink = Sink("Sink", clock) 

#     source_chapas.connect([buffer_chapas])
#     source_refuerzos.connect([buffer_refuerzos])
#     buffer_chapas.connect([welding])
#     buffer_refuerzos.connect([welding.get_component_input(0)])
#     welding.connect([sink])

#     clock.initialize()

#     last_time, elapsed_time = time.time(), 0
        
#     max_sim_time = 100
#     sim_time = 0
#     step = 10
    
#     while sim_time < max_sim_time:
#         clock.advance_clock(sim_time+step)        
#         sim_time = sim_time + step
        
#         if time.time() - last_time > 20:
#             elapsed_time+= time.time() - last_time
#             last_time = time.time()
#             print(f"Progress: {round(sim_time/max_sim_time*100,2)}%")
#             print(f"Elapsed Time: {elapsed_time}s")


#     print(f"\nSimulation Time: {clock.get_simulation_time()}")
#     print(f"Items processed: {sink.get_stats_collector().get_var_input_value()}") 
#     print(f"Items processed: {welding.get_stats_collector().get_var_output_value()}") 

#     print(f"Buffer Avg Staytime: {buffer_refuerzos.get_stats_collector().get_var_staytime_average()}")
#     print(f"Buffer Avg Queue Length: {buffer_refuerzos.get_stats_collector().get_var_content_average()}")


# if __name__ == "__main__":
#     test_MD1()
#     test_MM1()
#     test_multiAssembler()  
#     test_combiner() 
#     test_scheduleSource()
#     test_labelBasedPT()
#     test_combiner_basedOnLabel()  
#     test_MultipleLink_21()  
#     test_MultipleLink_12()  
#     test_MultipleLink_22()  

if __name__ == "__main__":
    unittest.main()