import unittest
from PyFlow import *
from unittest.mock import patch
# from parameterized import parameterized
from CEMI_PreviasCase import main

class TestCEMIPreviasCase(unittest.TestCase):

    @patch('time.time', return_value=0)  # Mocking time to avoid delays
    # @parameterized.expand([
    #     # Define multiple test cases with different inputs
    #     ("test_case_1", [50, 36, 74, 42], [1, 0, 0, 1]),  # First case
    #     ("test_case_2", [10, 20, 30, 40], [0, 1, 1, 0]),  # Second case
    #     ("test_case_3", [1, 2, 3, 4], [1, 1, 0, 0]),      # Third case
    # ])
    def test_simulation(self, mock_time):
        # Prepare sample inputs
        priorities = [50, 36, 74, 42, 45, 71, 51, 54, 4, 8, 35, 13, 10, 19, 9, 59, 49, 58, 23, 64, 76, 69, 60, 5, 21, 15, 89, 24, 30, 85, 68, 67, 34, 79, 28, 29, 80, 73, 37, 11, 48, 12, 22, 53, 81, 70, 47, 44, 38, 78, 90, 88, 77, 72, 57, 43, 20, 66, 18, 1, 6, 61, 33, 3, 65, 63, 83, 46, 55, 41, 31, 2, 62, 16, 52, 25, 84, 87, 75, 56, 27, 86, 82, 32, 14, 26, 17, 39, 7, 40]
        inspections = [1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 1, 1, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 0, 1, 1, 0, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 0, 0, 1, 1, 1, 1, 0, 1, 0, 1]

        # Initialize clock and sink objects manually, because we want to assert their values
        clock = SimClock.get_instance()  # Get the instance of SimClock
        sink = Sink("Sink", clock)  # Create a Sink object for stats

        # Run the main function
        main(priorities, inspections)

        # After simulation, we want to assert the values of simulation time and processed items
        expected_simulation_time = 100000  # Replace with the expected value
        expected_processed_items = 500  # Replace with the expected value

        # Get actual values after simulation
        actual_simulation_time = clock.get_simulation_time()
        actual_processed_items = sink.get_stats_collector().get_var_input_value()

        # Assert that the values are equal to the expected ones
        self.assertAlmostEqual(actual_simulation_time, 35550.20, "Simulation time doesn't match the expected value.")
        self.assertAlmostEqual(actual_processed_items, 90, "Processed items count doesn't match the expected value.")


if __name__ == "__main__":
    unittest.main()