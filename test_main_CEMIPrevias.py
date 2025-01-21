import unittest

import pandas as pd
from PyFlow import *
from unittest.mock import patch
from parameterized import parameterized
from CEMI_PreviasCase import main

def load_test_cases_from_excel(file_path):
    """Loads test cases from an Excel file with each case in a separate sheet."""
    test_cases = []
    # Open the Excel file
    excel_data = pd.ExcelFile(file_path)
    
    # Iterate through each sheet (each case)
    for sheet_name in excel_data.sheet_names:
        # Read the data from the sheet
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=0)
        
        # Extract fields from columns
        priorities = df["priorities"].dropna().astype(int).tolist()
        inspections = df["inspection"].dropna().astype(int).tolist()
        expected_n_inspecciones = int(df["n_inspecciones"].dropna().iloc[0])
        expected_n_retrasos = int(df["n_retrasos"].dropna().iloc[0])
        expected_sim_time = float(df["simTime"].dropna().iloc[0])
        
        # Add test case as a tuple
        test_cases.append((sheet_name, priorities, inspections, expected_sim_time, 90))
    
    return test_cases

class TestCEMIPreviasCase(unittest.TestCase):

# Load test cases from the Excel file
    test_cases = load_test_cases_from_excel("test_CEMIcase.xlsx")
    
    @parameterized.expand(test_cases)
    def test_simulation(self, case_name, priorities, inspections, expected_sim_time, expected_processed_items):
        """Tests the main function with multiple inputs."""
        # Run the main function
        clock, sink = main(priorities, inspections)

        # Assert results
        self.assertAlmostEqual(
            clock.get_simulation_time(), 
            expected_sim_time, 
            msg=f"{case_name}: Simulation time mismatch."
        )        
        self.assertEqual(
            sink.get_stats_collector().get_var_input_value(), 
            expected_processed_items, 
            msg=f"{case_name}: Processed items mismatch."
        )

if __name__ == "__main__":
    unittest.main()