import time
import unittest
from PyFlow import *
from scipy import stats
import sys

class TestLabelBasedModels(unittest.TestCase):

    def setUp(self):
        # This method will run before each test to set up the environment
        SimClock._instance =  None
        self.clock = SimClock.get_instance()
        self.max_sim_time = 100

    def test_labelBasedPT(self):
        test_cases = [
                # (Schedule Source DataBase, PT label value, Queue Size, Expected Output)
                ("Data\\model_scheduleSource.xlsx", 5, 1, 13)  
            ]
        
        for data in test_cases:
            print(f"\n - Test Label-based PT:")

            model_item = Item(0, labels={"PT": "5"}, model_item=True) # PT refers to process time.
            source1 = ScheduleSource("Source", self.clock, file_name=data[0], model_item=model_item)
            buffer1 = ItemsQueue(data[2], "Queue", self.clock)
            
            processor = MultiServer(1, "item.get_label_value('PT')", "Process", self.clock)
            sink = Sink("Sink", self.clock) 

            source1.connect([buffer1])
            buffer1.connect([processor])
            processor.connect([sink])

            self.clock.initialize()

            self.clock.advance_clock(self.max_sim_time)   

            print(f"\nSimulation Time: {self.clock.get_simulation_time()}")
            print(f"Items processed: {sink.get_stats_collector().get_var_input_value()}") 
            print(f"Items processed: {processor.get_stats_collector().get_var_output_value()}") 

            print(f"Buffer Avg Staytime: {buffer1.get_stats_collector().get_var_staytime_average()}")
            print(f"Buffer Avg Queue Length: {buffer1.get_stats_collector().get_var_content_average()}")

            # Assertions (you can adjust these based on expected results)
            self.assertEqual(sink.get_stats_collector().get_var_input_value(), data[3])


        
    def test_combinerBasedOnLabel(self):
        test_cases = [
                # (Schedule Source 1 DataBase, chedule Source 2 DataBase, Queue 1 Size, Queue 2 Size, Welding Dist, Expected Output)
                ("Data\\test_combinerBasedOnLabel_chapas.data", "Data\\test_combinerBasedOnLabel_refuerzos.data", 1000, 1000, stats.expon(scale=4), 4)  
            ]
 
        for data in test_cases:
            print(f"\n - Test Label-based Combiner List:")

            chapa_item = Item(0, name = "Chapa", model_item=True)
            refuerzo_item = Item(0, name="previa", model_item=True)
            source_chapas = ScheduleSource("Source", self.clock, file_name=data[0], model_item=chapa_item)
            source_refuerzos = ScheduleSource("Source", self.clock, file_name=data[1],  model_item=refuerzo_item)
            buffer_chapas = ItemsQueue(data[2], "Queue", self.clock)
            buffer_refuerzos = ItemsQueue(data[3], "Queue", self.clock)
            
            welding = Combiner([1], data[4], "item.get_label_value('Soldadura')", self.clock, pull_mode=SingleLabelStrategy("Previa_ID"), 
                            update_requirements = True, update_labels=["nRefuerzos"])
            sink = Sink("Sink", self.clock) 

            source_chapas.connect([buffer_chapas])
            source_refuerzos.connect([buffer_refuerzos])
            buffer_chapas.connect([welding])
            buffer_refuerzos.connect([welding.get_component_input(0)])
            welding.connect([sink])

            self.clock.initialize()

            self.clock.advance_clock(self.max_sim_time)

            print(f"\nSimulation Time: {self.clock.get_simulation_time()}")
            print(f"Items processed: {sink.get_stats_collector().get_var_input_value()}") 
            print(f"Items processed: {welding.get_stats_collector().get_var_output_value()}") 

            print(f"Buffer Avg Staytime: {buffer_refuerzos.get_stats_collector().get_var_staytime_average()}")
            print(f"Buffer Avg Queue Length: {buffer_refuerzos.get_stats_collector().get_var_content_average()}")

            # Assertions (you can adjust these based on expected results)
            self.assertEqual(sink.get_stats_collector().get_var_input_value(), data[5])


if __name__ == "__main__":
    unittest.main()