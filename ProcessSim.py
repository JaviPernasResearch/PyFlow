import logging
import DOE
import sys

logging.basicConfig(level=logging.INFO)
logger=logging.getLogger(__name__)

class ProcessSim:
    
    def main():
        experiment = DOE()  # Crear una nueva instancia de DOE
        
        experiment.runs = 5  # Establecer el número de corridas a 5
        
        experiment.load_scenarios("doe.txt")  # Cargar los escenarios desde el archivo "doe.txt"
        
        experiment.run_experimentation()  # Ejecutar la experimentación
        
        sys.exit(0)  # Terminar el programa

if __name__ == "__main__":
    ProcessSim.main()  # Llamar al método main
