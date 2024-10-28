from typing import List
import logging

import SerialLine

##Prueba

class DOE:
    def __init__(self, runs:int):
        self.scenarios :List[str]= []
        self.runs = 0
        self.logger=logging.getLogger(__name__)

    def load_scenarios(self, file_name_:str)->None:
        try:
            with open(file_name_, 'r', encoding='ascii') as file:
                self.scenarios = file.readlines()
        except FileNotFoundError:
            self.logger.error(f"Error loading file:{file_name_} not found")
            print("Error loading file")
        except Exception as e:
            self.logging.error(f"An error ocurred while loading scenarios {e}")
            print("Error loading file")

    def run_experimentation(self)->None:
        the_line = SerialLine()  

        try:
            with open("summary.txt", 'w', encoding='ascii') as writer:

                 for treatment in self.scenarios:
                    treatment = treatment.strip()  # Eliminar espacios y saltos de línea
                    the_line.load_scenario(treatment)
                    the_line.generate_elements()

                    print(f"Start Treatment: {treatment}")

                    for i in range(self.runs):
                        print(".", end='', flush=True)  # Imprimir punto sin salto de línea
                        the_line.reset()
                        clock=the_line.get_clock()
                        clock.reset()

                        while clock.advance_clock(1000):
                            pass

                        summary=the_line.report_summary()
                        writer.write(f"{treatment}\t{i}\t{summary}\t{clock.get_simulation_time()}\n")
                        writer.flush()

                    print("Treatment Completed")

        except Exception as e:
            self.logging.error(f"An error occurred while writing to summary.txt: {e}")
            print("Could not write to file")
            return

