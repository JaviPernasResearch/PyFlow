# import unittest
# from PyFlow import *
# from scipy import stats

# class TestCEMIPreviasCase(unittest.TestCase):

#     def setUp(self):
#         self.chapa_item = Item(0, name="Chapa", model_item=True)
#         self.refuerzo_item = Item(0, name="previa", model_item=True)


#     def run_simulation(self, priorities, inspections):
#         SimClock._instance = None
#         self.clock = SimClock.get_instance()

#         chapas = SeqOptTools.read_excel_to_dict("CEMI_chapas.xlsx", "MBOM")
#         SeqOptTools.add_labels_to_dict(chapas, "inspeccionOn", inspections)
#         chapas_reordered = SeqOptTools.transform_sequence(chapas, priorities)

#         refuerzos = SeqOptTools.read_excel_to_dict("CEMI_refuerzos.xlsx", "MBOM")
#         refuerzos_reordered = SeqOptTools.transform_sequence(refuerzos, priorities)

#         source_chapas = ScheduleSource("SourceChapas", self.clock, model_item=self.chapa_item, data_dict=chapas_reordered)
#         source_refuerzos = ScheduleSource("SourceRefuerzos", self.clock, model_item=self.refuerzo_item, data_dict=refuerzos_reordered)
#         buffer_chapas = ItemsQueue(1000, "QueueChapas", self.clock)
#         buffer_refuerzos = ItemsQueue(1000, "QueueRefuerzos", self.clock)

#         welding = Combiner([1], "item.get_label_value('tSoldadura') + item.get_label_value('tInspeccion')* item.get_label_value('inspeccionOn')", 
#                            "Welding", self.clock, pull_mode=SingleLabelStrategy("Referencia"), update_requirements=True, 
#                            update_labels=["nRefuerzos"])
        
#         self.sink = Sink("Sink", self.clock)
        
#         source_chapas.connect([buffer_chapas])
#         source_refuerzos.connect([buffer_refuerzos])
#         buffer_chapas.connect([welding])
#         buffer_refuerzos.connect([welding.get_component_input(0)])
#         welding.connect([self.sink])

#         self.clock.initialize()

#         max_sim_time = 100000
#         sim_time = 0
#         step = 10

#         while sim_time < max_sim_time:
#             self.clock.advance_clock(sim_time + step)
#             sim_time += step

#     def test_priorities_test1(self):
#         priorities_test1 = [50, 36, 74, 42, 45, 71, 51, 54, 4, 8, 35, 13, 10, 19, 9, 59, 49, 58, 23, 64, 76, 69, 60, 5, 21, 15, 89, 24, 30, 85, 68, 67, 34, 79, 28, 29, 80, 73, 37, 11, 48, 12, 22, 53, 81, 70, 47, 44, 38, 78, 90, 88, 77, 72, 57, 43, 20, 66, 18, 1, 6, 61, 33, 3, 65, 63, 83, 46, 55, 41, 31, 2, 62, 16, 52, 25, 84, 87, 75, 56, 27, 86, 82, 32, 14, 26, 17, 39, 7, 40]
#         inspections_test1 = [1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 1, 1, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 0, 1, 1, 0, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 0, 0, 1, 1, 1, 1, 0, 1, 0, 1]
#         self.run_simulation(priorities_test1, inspections_test1)
#         self.assertEqual(self.sink.get_stats_collector().get_var_input_value(), 90)
#         self.assertAlmostEqual(self.clock.get_simulation_time(), 35550.20)

#     def test_priorities_test2(self):
#         priorities_test2 = [33, 58, 30, 86, 85, 4, 76, 57, 2, 68, 19, 72, 80, 73, 79, 20, 10, 22, 46, 15, 82, 37, 56, 36, 59, 69, 14, 53, 64, 70, 32, 67, 9, 54, 55, 87, 16, 78, 48, 27, 89, 65, 43, 50, 7, 13, 23, 42, 8, 62, 88, 83, 38, 66, 35, 12, 26, 41, 49, 71, 17, 51, 44, 25, 63, 3, 84, 45, 29, 6, 90, 1, 52, 74, 18, 24, 5, 11, 39, 60, 34, 28, 31, 61, 40, 77, 21, 75, 81, 47]
#         inspections_test2 = [0, 0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 1, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1, 1, 0, 1, 1, 0, 0, 1, 0, 0, 1, 1, 0, 1, 1, 0, 1, 1, 1, 0, 0, 1, 1, 1, 1, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 0, 0, 1, 1, 1, 1, 1, 0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 1, 1, 0, 0, 1, 0, 0]
#         self.run_simulation(priorities_test2, inspections_test2)
#         self.assertEqual(self.sink.get_stats_collector().get_var_input_value(), 90)
#         self.assertAlmostEqual(self.clock.get_simulation_time(), 32575.8)

#     def test_priorities_test3(self):
#         priorities_test3 = [19, 53, 55, 54, 24, 58, 56, 70, 20, 89, 5, 32, 62, 64, 87, 72, 82, 44, 79, 47, 48, 30, 61, 60, 63, 29, 68, 81, 25, 80, 36, 14, 74, 71, 39, 66, 65, 18, 6, 84, 38, 46, 35, 83, 88, 41, 49, 51, 85, 22, 50, 16, 28, 45, 15, 8, 78, 4, 75, 2, 11, 86, 37, 90, 40, 67, 9, 57, 26, 1, 42, 59, 31, 34, 21, 10, 12, 77, 3, 76, 17, 13, 73, 52, 43, 23, 33, 69, 27, 7]
#         inspections_test3 = [0, 0, 0, 1, 0, 1, 1, 1, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 0, 0, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 0, 1, 1, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0, 0, 0, 1, 1, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1]
#         self.run_simulation(priorities_test3, inspections_test3)
#         self.assertEqual(self.sink.get_stats_collector().get_var_input_value(), 90)
#         self.assertAlmostEqual(self.clock.get_simulation_time(), 32745.8)

#     def test_priorities_test4(self):
#         priorities_test4 = [34, 62, 71, 69, 26, 47, 12, 25, 32, 66, 44, 23, 58, 29, 84, 18, 76, 43, 22, 7, 27, 87, 89, 13, 75, 80, 74, 85, 11, 68, 73, 21, 55, 88, 40, 33, 56, 2, 4, 19, 17, 64, 31, 9, 50, 5, 46, 78, 35, 63, 61, 77, 54, 67, 83, 36, 48, 6, 16, 14, 53, 65, 81, 59, 39, 49, 79, 20, 37, 24, 30, 28, 1, 57, 70, 72, 42, 10, 52, 3, 15, 86, 90, 41, 82, 8, 38, 60, 45, 51]
#         inspections_test4 = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 1, 0]
#         self.run_simulation(priorities_test4, inspections_test4)
#         self.assertEqual(self.sink.get_stats_collector().get_var_input_value(), 90)
#         self.assertAlmostEqual(self.clock.get_simulation_time(), 21454.6)

# if __name__ == "__main__":
#     unittest.main()