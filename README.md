# PyFlow

PyFlow is an open-source, Python-based discrete-event simulation (DES) engine designed specifically for modeling and optimizing industrial manufacturing systems. Developed with accessibility, modularity, and integration in mind, PyFlow enables rapid simulation model development and seamless interoperability with machine learning (ML) and optimization libraries.

This repository contains the source code of PyFlow, documentation, and examples, including a real-world case study from the shipbuilding industry.

## Features

- Lightweight, object-oriented architecture for high modularity and extensibility
- Native Python implementation for easy integration with ML and optimization frameworks
- Designed specifically for manufacturing: includes elements like sources, queues, processors, assemblers, resources, and more
- Easy model development and experimentation
- Excel-based interface for simplified simulation model definition (under development)
- Real-world case study included (robotic welding cell in shipbuilding)

## Architecture Overview

PyFlow is structured into the following main modules:

- **SimClock**: Handles event execution and simulation time control
- **Elements**: Includes all fixed simulation components (queues, processors, etc.)
- **Link**: Manages object routing and flow connections
- **Items**: Defines moving parts in the system (e.g., parts, assemblies)
- **Statistics**: Tracks key performance indicators (KPI) such as throughput, waiting time, etc.
- **Resources**: Manages constraints like operators or robotic arms
- **Optimization & RandomEvents** (in progress): Enable dynamic simulation behavior and connection with external ML libraries

PyFlow minimizes external dependencies for core simulation to ensure portability and maintainability.

## Case Study Example

The repository includes a real-world case study involving a robotic welding cell in shipbuilding, developed in collaboration with Navantia. This case demonstrates how PyFlow can be integrated with optimization and sequencing algorithms to maximize throughput and visual inspection under time constraints.

## Prerequisites

- Python 3.8+
- Dependencies listed in `requirements.txt`

# Installation

Clone the repository and install dependencies:

'''bash
git clone https://github.com/your-username/PyFlow.git
cd PyFlow
pip install -r requirements.txt

> Note: PyFlow is compatible with Python 3.8 and above.

## Running an Example

You can find example models in the `examples/` folder. To run a simple simulation model, use:

'''bash
python examples/example_model.py

Make sure all dependencies are installed and the `SimClock` environment is initialized before building your model.

## Contributing to PyFlow

We welcome contributions! To contribute to **PyFlow**, follow these steps:

1. Fork this repository.
2. Create a branch:  
   '''bash
   git checkout -b feature/your-feature-name
3. Make your changes and commit them:  
   '''bash
   git commit -m "Add feature: description of your change"
4. Push your changes:  
   '''bash
   git push origin feature/your-feature-name
5. Create a pull request on GitHub.

More details are available in [CONTRIBUTING.md](CONTRIBUTING.md).

## Case Study Example

Included in this repository is a real-world case study involving a robotic welding cell for shipbuilding. The simulation integrates sequencing and optimization algorithms to:
- Maximize the number of visual inspections
- Stay within time constraints
- Respond to disruptions dynamically

This use case demonstrates how PyFlow can replace commercial tools like Plant Simulation while ensuring seamless integration with ML and optimization libraries.

## Contributors

Thanks to the following people who have contributed to this project:

- [Javier Pernas-Álvarez](https://pdi.udc.es/en/File/Pdi/HF9NK) 📖  
- [Diego Crespo-Pereira](https://pdi.udc.es/en/File/Pdi/6W6MH) 📖  

## Contact

For questions, suggestions, or feedback, contact:

**Javier Pernas-Álvarez**  
Email: javier.pernas2@udc.es  
Affiliation: Universidade da Coruña

## License

This project is licensed under the [GNU GPLv3](https://choosealicense.com/licenses/gpl-3.0/).
