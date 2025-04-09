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

## Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/your-username/PyFlow.git
cd PyFlow
pip install -r requirements.txt

## Contributors

Thanks to the following people who have contributed to this project:

* [Javier Pernas-Álvarez](https://pdi.udc.es/en/File/Pdi/HF9NK) 📖
* [Diego Crespo-Pereira](https://pdi.udc.es/en/File/Pdi/6W6MH) 📖


## Contact

If you want to contact me you can reach me at <javier.pernas2@udc.es>.

## License
<!--- If you're not sure which open license to use see https://choosealicense.com/--->

This project uses the following license: [GNU GPLv3](https://choosealicense.com/licenses/gpl-3.0/).
