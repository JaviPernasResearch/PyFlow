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

# def test_MultipleLink_21():
#     print(f"\n - Test Multiple Link 2-1:")

#     First we create the clock
#     clock = SimClock.get_instance()

#     arrival_distribution = stats.uniform(loc=2, scale = 0)

#     source1 = InterArrivalSource("Source", clock, arrival_distribution)
#     source2 = InterArrivalSource("Source", clock, arrival_distribution)
#     buffer = ItemsQueue(100000, "Queue", clock)
#     sink = Sink("Sink", clock) 

#     process_distribution = stats.uniform(loc=2,scale=0)
#     procesor = MultiServer(1, process_distribution, "Procesador", clock)

#     There are two ways of making multiple connections
#     Way 1: Using the static connect_multiple method
#     Element.connect_multiple([source1, source2], [buffer])
#     Way 2: Using the connect method of the element (uncomment the following lines and comment the previous one)
#     source1.connect([buffer])
#     source2.connect([buffer])
    
#     buffer.connect([procesor])
#     procesor.connect([sink])

#     After connecting the elements, we must initialize the simulation
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

#     print(f"Buffer Avg Staytime: {buffer.get_stats_collector().get_var_staytime_average()}")
#     print(f"Buffer Avg Queue Length: {buffer.get_stats_collector().get_var_content_average()}")

# def test_MultipleLink_12():
#     print(f"\n - Test Multiple Link 1-2:")

#     First we create the clock
#     clock = SimClock.get_instance()

#     arrival_distribution = stats.uniform(loc=2, scale = 0)

#     source1 = InterArrivalSource("Source", clock, arrival_distribution)
#     buffer1 = ItemsQueue(3, "Queue1", clock)
#     buffer2 = ItemsQueue(3, "Queue2", clock)
#     sink = Sink("Sink", clock) 

#     process_distribution = stats.uniform(loc=2,scale=0)
#     procesor1 = MultiServer(1, process_distribution, "Procesador1", clock)
#     procesor2 = MultiServer(1, process_distribution, "Procesador2", clock)

#     Element.connect_multiple([source1], [buffer1, buffer2])
#     source1.connect([buffer1])
#     source1.connect([buffer2])
#     buffer1.connect([procesor1])
#     buffer2.connect([procesor2])
#     procesor1.connect([sink])
#     procesor2.connect([sink])

#     After connecting the elements, we must initialize the simulation
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

#     print(f"Buffer1 Avg Staytime: {buffer1.get_stats_collector().get_var_staytime_average()}")
#     print(f"Buffer1 Avg Queue Length: {buffer1.get_stats_collector().get_var_content_average()}")
#     print(f"Buffer1 Output: {buffer1.get_stats_collector().get_var_output_value()}")
#     print(f"Buffer2 Avg Staytime: {buffer2.get_stats_collector().get_var_staytime_average()}")
#     print(f"Buffer2 Avg Queue Length: {buffer2.get_stats_collector().get_var_content_average()}")
#     print(f"Buffer2 Output: {buffer2.get_stats_collector().get_var_output_value()}")

# def test_MultipleLink_22():
#     print(f"\n - Test Multiple Link 2-2:")

#     First we create the clock
#     clock = SimClock.get_instance()

#     arrival_distribution = stats.uniform(loc=2, scale = 0)

#     source1 = InterArrivalSource("Source1", clock, arrival_distribution)
#     source2 = InterArrivalSource("Source2", clock, arrival_distribution)
#     source1 = InfiniteSource(name= "Source1", clock=clock)
#     source2 = InfiniteSource(name= "Source2", clock=clock)

#     buffer1 = ItemsQueue(3, "Queue1", clock)
#     buffer2 = ItemsQueue(3, "Queue2", clock)
#     sink = Sink("Sink", clock) 

#     process_distribution1 = stats.uniform(loc=20,scale=0)
#     process_distribution2 = stats.uniform(loc=10,scale=0)
#     procesor1 = MultiServer(1, process_distribution1, "Procesador1", clock)
#     procesor2 = MultiServer(1, process_distribution2, "Procesador2", clock)

#     Element.connect_multiple([source1, source2], [buffer1, buffer2])
#     source1.connect([buffer1, buffer2])
#     source2.connect([buffer2, buffer1])
#     buffer1.connect([procesor1])
#     buffer2.connect([procesor2])
#     procesor1.connect([sink])
#     procesor2.connect([sink])

#     After connecting the elements, we must initialize the simulation
#     clock.initialize()

#     last_time, elapsed_time = time.time(), 0
        
#     max_sim_time = 100
#     sim_time = 0
#     step = 1
    
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

#     print(f"Buffer1 Avg Staytime: {buffer1.get_stats_collector().get_var_staytime_average()}")
#     print(f"Buffer1 Avg Queue Length: {buffer1.get_stats_collector().get_var_content_average()}")
#     print(f"Buffer1 Output: {buffer1.get_stats_collector().get_var_output_value()}")
#     print(f"Buffer2 Avg Staytime: {buffer2.get_stats_collector().get_var_staytime_average()}")
#     print(f"Buffer2 Avg Queue Length: {buffer2.get_stats_collector().get_var_content_average()}")
#     print(f"Buffer2 Output: {buffer2.get_stats_collector().get_var_output_value()}")

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