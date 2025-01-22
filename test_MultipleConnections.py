import time
import unittest
from PyFlow import *
from scipy import stats
import sys

class TestMultipleConnections(unittest.TestCase):

    def setUp(self):
        # This method will run before each test to set up the environment
        SimClock._instance =  None
        self.clock = SimClock.get_instance()
        self.max_sim_time = 100
        self.step = 10
        self.sim_time = 0

    def test_MultipleLink_21(self):
        test_cases = [
                    # (arrival_dist, Queue Size, process_dist, Expected Output)
                    (2, 100000, 2, 49)  
                ]
        
        for data in test_cases:
            print(f"\n - Test Multiple Link 2-1:")

            source1 = InterArrivalSource("Source", self.clock, data[0])
            source2 = InterArrivalSource("Source", self.clock, data[0])
            buffer = ItemsQueue(data[1], "Queue", self.clock)
            sink = Sink("Sink", self.clock) 

            procesor = MultiServer(1, data[2], "Procesador", self.clock)

            # There are two ways of making multiple connections
                # Way 1: Using the static connect_multiple method
            Element.connect_multiple([source1, source2], [buffer])
                # Way 2: Using the connect method of the element (uncomment the following lines and comment the previous one)
                # This way is tested in other tests.
            # source1.connect([buffer])
            # source2.connect([buffer])
            
            buffer.connect([procesor])
            procesor.connect([sink])

            self.clock.initialize()

            self.clock.advance_clock(self.max_sim_time)   

            print(f"\nSimulation Time: {self.clock.get_simulation_time()}")
            print(f"Items processed: {sink.get_stats_collector().get_var_input_value()}") 

            print(f"Buffer Avg Staytime: {buffer.get_stats_collector().get_var_staytime_average()}")
            print(f"Buffer Avg Queue Length: {buffer.get_stats_collector().get_var_content_average()}")
            
            # Assertions (you can adjust these based on expected results)
            self.assertEqual(sink.get_stats_collector().get_var_input_value(), data[3])

    def test_MultipleLink_12(self):
        test_cases = [
                    # (arrival_dist, Queue Size, process_dist, Expected Output Buffer1, Expected Output Buffer2, Expected Output Sink)
                    (2, 3, 2, 50, 0, 49)  
                ]
        
        for data in test_cases:

            print(f"\n - Test Multiple Link 1-2:")

            source1 = InterArrivalSource("Source", self.clock, data[0])
            buffer1 = ItemsQueue(data[1], "Queue1", self.clock)
            buffer2 = ItemsQueue(data[1], "Queue2", self.clock)
            sink = Sink("Sink", self.clock) 

            procesor1 = MultiServer(1, data[2], "Procesador1", self.clock)
            procesor2 = MultiServer(1, data[2], "Procesador2", self.clock)

            Element.connect_multiple([source1], [buffer1, buffer2])
            source1.connect([buffer1])
            source1.connect([buffer2])
            buffer1.connect([procesor1])
            buffer2.connect([procesor2])
            procesor1.connect([sink])
            procesor2.connect([sink])

            self.clock.initialize()

            self.clock.advance_clock(self.max_sim_time)   

            print(f"\nSimulation Time: {self.clock.get_simulation_time()}")
            print(f"Items processed: {sink.get_stats_collector().get_var_input_value()}") 

            print(f"Buffer1 Avg Staytime: {buffer1.get_stats_collector().get_var_staytime_average()}")
            print(f"Buffer1 Avg Queue Length: {buffer1.get_stats_collector().get_var_content_average()}")
            print(f"Buffer1 Output: {buffer1.get_stats_collector().get_var_output_value()}")
            print(f"Buffer2 Avg Staytime: {buffer2.get_stats_collector().get_var_staytime_average()}")
            print(f"Buffer2 Avg Queue Length: {buffer2.get_stats_collector().get_var_content_average()}")
            print(f"Buffer2 Output: {buffer2.get_stats_collector().get_var_output_value()}")

            # Assertions (you can adjust these based on expected results)
            self.assertEqual(buffer1.get_stats_collector().get_var_output_value(), data[3])
            self.assertEqual(buffer2.get_stats_collector().get_var_output_value(), data[4])
            self.assertEqual(sink.get_stats_collector().get_var_input_value(), data[5])


    def test_MultipleLink_22(self):
        test_cases = [
                    # (Queue Size, process1_dist, process2_dist, Expected Output Buffer1, Expected Output Buffer2, Expected Output Sink)
                    (3, 20, 10, 6, 11, 15)  
                ]
        for data in test_cases:

            print(f"\n - Test Multiple Link 2-2:")

            source1 = InfiniteSource(name= "Source1",clock=self.clock)
            source2 = InfiniteSource(name= "Source2", clock=self.clock)

            buffer1 = ItemsQueue(data[0], "Queue1", self.clock)
            buffer2 = ItemsQueue(data[0], "Queue2", self.clock)
            sink = Sink("Sink", self.clock) 
            procesor1 = MultiServer(1, data[1], "Procesador1", self.clock)
            procesor2 = MultiServer(1, data[2], "Procesador2", self.clock)

            Element.connect_multiple([source1, source2], [buffer1, buffer2])
            source1.connect([buffer1, buffer2])
            source2.connect([buffer2, buffer1])
            buffer1.connect([procesor1])
            buffer2.connect([procesor2])
            procesor1.connect([sink])
            procesor2.connect([sink])

            self.clock.initialize()

            self.clock.advance_clock(self.max_sim_time)   

            print(f"\nSimulation Time: {self.clock.get_simulation_time()}")
            print(f"Items processed: {sink.get_stats_collector().get_var_input_value()}") 

            print(f"Buffer1 Avg Staytime: {buffer1.get_stats_collector().get_var_staytime_average()}")
            print(f"Buffer1 Avg Queue Length: {buffer1.get_stats_collector().get_var_content_average()}")
            print(f"Buffer1 Output: {buffer1.get_stats_collector().get_var_output_value()}")
            print(f"Buffer2 Avg Staytime: {buffer2.get_stats_collector().get_var_staytime_average()}")
            print(f"Buffer2 Avg Queue Length: {buffer2.get_stats_collector().get_var_content_average()}")
            print(f"Buffer2 Output: {buffer2.get_stats_collector().get_var_output_value()}")

            # Assertions (you can adjust these based on expected results)
            self.assertEqual(buffer1.get_stats_collector().get_var_output_value(), data[3])
            self.assertEqual(buffer2.get_stats_collector().get_var_output_value(), data[4])
            self.assertEqual(sink.get_stats_collector().get_var_input_value(), data[5])


if __name__ == "__main__":
    unittest.main()