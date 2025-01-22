import time
import unittest
from PyFlow import *
from scipy import stats
import sys

class TestBasicModels(unittest.TestCase):

    def setUp(self):
        # This method will run before each test to set up the environment
        SimClock._instance =  None
        self.clock = SimClock.get_instance()
        self.max_sim_time = 100

    def test_MD1(self):
        test_cases = [
            (stats.expon(scale=5), 100000, stats.uniform(loc=2, scale=0), 10, 40, 0.5)  # Example for MD1
        ]
        
        print(f"\n - Test MD1:")

        for data in test_cases:

            source = InterArrivalSource("Source", self.clock, data[0])
            buffer = ItemsQueue(data[1], "Queue", self.clock)
            sink = Sink("Sink", self.clock) 

            procesor = MultiServer(1, data[2], "Procesador", self.clock)

            source.connect([buffer])
            buffer.connect([procesor])
            procesor.connect([sink])

            #After connecting the elements, we must initialize the simulation
            self.clock.initialize()
            
            self.clock.advance_clock(self.max_sim_time)       

            print(f"\nSimulation Time: {self.clock.get_simulation_time()}")
            print(f"Items processed: {sink.get_stats_collector().get_var_input_value()}") 
            print(f"Buffer Avg Staytime: {buffer.get_stats_collector().get_var_staytime_average()}")
            print(f"Buffer Avg Queue Length: {buffer.get_stats_collector().get_var_content_average()}")

            # Assertions
            self.assertTrue(data[3]<sink.get_stats_collector().get_var_input_value()<data[4])
            self.assertTrue(buffer.get_stats_collector().get_var_content_average() < data[5])

    def test_MM1(self):
        test_cases = [
            (stats.expon(scale=2), 100, stats.expon(scale=2), 25, 60, 0, 1)  # Example for MD1
        ]

        for data in test_cases:
            print(f"\n - Test MM1:")


            source = InterArrivalSource("Source", self.clock, data[0])
            buffer = ItemsQueue(data[1], "Queue", self.clock)
            sink = Sink("Sink", self.clock) 

            procesor = MultiServer(1, data[2], "Procesador", self.clock)

            source.connect([buffer])
            buffer.connect([procesor])
            procesor.connect([sink])

            self.clock.initialize()
            
            self.clock.advance_clock(self.max_sim_time)       

            print(f"\nSimulation Time: {self.clock.get_simulation_time()}")
            print(f"Items processed: {sink.get_stats_collector().get_var_input_value()}") 
            print(f"Buffer Avg Staytime: {buffer.get_stats_collector().get_var_staytime_average()}")
            print(f"Buffer Avg Queue Length: {buffer.get_stats_collector().get_var_content_average()}")

            # Assertions
            self.assertTrue(data[3]<sink.get_stats_collector().get_var_input_value()<data[4])
            self.assertTrue(data[5]<=buffer.get_stats_collector().get_var_content_average()<=data[6])

    def test_multiAssembler(self):
        test_cases = [
            (stats.uniform(loc=4, scale=0), stats.expon(scale=4), 100, 15, 30, 0, 1) 
        ]

        for data in test_cases:
            print(f"\n - Test MultiAssembler:")

            # Setting up the source and buffers
            source1 = InterArrivalSource("Source", self.clock, data[0])
            source2 = InterArrivalSource("Source", self.clock, data[0])
            buffer1 = ItemsQueue(data[2], "Queue", self.clock)
            buffer2 = ItemsQueue(data[2], "Queue", self.clock)
            sink = Sink("Sink", self.clock)

            # Setting up the MultiAssembler with process distribution
            MAssembler = MultiAssembler(1, [1, 1], data[1], "MultiAssembler", self.clock)

            # Connecting components
            source1.connect([buffer1])
            source2.connect([buffer2])
            buffer1.connect([MAssembler.get_component_input(0)])
            buffer2.connect([MAssembler.get_component_input(1)])
            MAssembler.connect([sink])

            # Initializing the clock and simulation
            self.clock.initialize()  
            self.clock.advance_clock(self.max_sim_time)   

            print(f"\nSimulation Time: {self.clock.get_simulation_time()}")
            print(f"Items processed: {sink.get_stats_collector().get_var_input_value()}") 
            print(f"Buffer Avg Staytime: {buffer1.get_stats_collector().get_var_staytime_average()}")
            print(f"Buffer Avg Queue Length: {buffer1.get_stats_collector().get_var_content_average()}")

            # Assertions (you can adjust these based on expected results)
            self.assertTrue(data[3] < sink.get_stats_collector().get_var_input_value() < data[4])
            self.assertTrue(data[5] <= buffer1.get_stats_collector().get_var_content_average() <= data[6])

    def test_combiner(self):
        test_cases = [
            (stats.uniform(loc=2,scale=0), stats.expon(scale=4), 100, 15, 30, 1) 
        ]

        for data in test_cases:

            print(f"\n - Test Combiner:")

            self.clock = SimClock.get_instance()

            arrival_distribution = data[0]

            source1 = InterArrivalSource("Source", self.clock, arrival_distribution)
            source2 = InterArrivalSource("Source", self.clock, arrival_distribution)
            buffer1 = ItemsQueue(data[2], "Queue", self.clock)
            buffer2 = ItemsQueue(data[2], "Queue", self.clock)
            sink = Sink("Sink", self.clock) 

            combiner = Combiner([2], data[1], "Combiner", self.clock)

            source1.connect([buffer1])
            source2.connect([buffer2])
            buffer1.connect([combiner])
            buffer2.connect([combiner.get_component_input(0)])
            combiner.connect([sink])

            self.clock.initialize()
            self.clock.advance_clock(self.max_sim_time)   


            print(f"\nSimulation Time: {self.clock.get_simulation_time()}")
            print(f"Items processed: {sink.get_stats_collector().get_var_input_value()}") 
            print(f"Items processed: {combiner.get_stats_collector().get_var_output_value()}") 

            print(f"Buffer Avg Staytime: {buffer1.get_stats_collector().get_var_staytime_average()}")
            print(f"Buffer Avg Queue Length: {buffer1.get_stats_collector().get_var_content_average()}")

            # Assertions (you can adjust these based on expected results)
            self.assertTrue(data[3] < sink.get_stats_collector().get_var_input_value() < data[4])
            self.assertTrue(buffer1.get_stats_collector().get_var_content_average() <= data[5])

    def test_scheduleSource(self):
        test_cases = [
            ("Data\\model_scheduleSource.csv", stats.expon(scale=4), 1, 4),
            ("Data\\model_scheduleSource.data", stats.expon(scale=4), 1, 4) 
        ]

        for data in test_cases:
            print(f"\n - Test ScheduleSource:")

            model_item = Item(0, labels={"Test": "Label1"}, model_item=True)
            source1 = ScheduleSource("Source", self.clock, file_name=data[0], model_item=model_item)
            # source1 = ScheduleSource("Source", self.clock, "Data\test_scheduleSource.data", model_item)
            buffer1 = ItemsQueue(data[2], "Queue", self.clock)
            processor = MultiServer(1, data[1], "Process", self.clock)
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

if __name__ == "__main__":
    unittest.main()