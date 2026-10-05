"""Run every standard manufacturing line once and print a short report.

    python examples/standard_lines.py
"""
from PyFlow import QueueSizeStrategy
from PyFlow.standard_lines import (Stage, assembly_line, kit_assembly, multi_product_flow_shop,
                                   order_release_line, parallel_machines, product_routing,
                                   serial_line, single_station)

SEED = 1

CASES = {
    "M/M/1 (rho = 0.8)": lambda: single_station(arrival="Exponential~0.8", service="Exponential~1", seed=SEED),
    "M/M/2 (rho = 0.8)": lambda: single_station(arrival="Exponential~1.6", service="Exponential~1", servers=2, seed=SEED),
    "M/D/1 (rho = 0.8)": lambda: single_station(arrival="Exponential~0.8", service=1, seed=SEED),
    "Serial line, finite buffers": lambda: serial_line(
        arrival="Exponential~1",
        stages=[Stage("Triangular~0.5~0.7~1.0"), Stage("Triangular~0.6~0.8~1.1", buffer=3),
                Stage("Normal~0.7~0.1", buffer=3)],
        seed=SEED),
    "Parallel machines, shortest queue": lambda: parallel_machines(
        arrival="Exponential~0.8", services=["ExponentialMean~1.5", "ExponentialMean~3"],
        strategy=QueueSizeStrategy(), seed=SEED),
    "Assembly (2 components per unit)": lambda: assembly_line(
        main_arrival="Exponential~0.4", component_arrival="Exponential~0.9", components_per_unit=2,
        assembly_time="Uniform~1~2", final_stages=[Stage("ExponentialMean~1.5", buffer=5)], seed=SEED),
    "Kit assembly (1 + 2)": lambda: kit_assembly(
        arrivals=["Exponential~0.4", "Exponential~0.9"], requirements=[1, 2], assembly_time="Uniform~1~2", seed=SEED),
    "Multi-product flow shop": lambda: multi_product_flow_shop(
        products={"A": {"arrival": "Exponential~0.1", "PT1": 2, "PT2": 3},
                  "B": {"arrival": "Exponential~0.1", "PT1": 3, "PT2": 2},
                  "C": {"arrival": "Exponential~0.1", "PT1": 4, "PT2": 1}},
        stations=2, seed=SEED),
    "Product routing by label": lambda: product_routing(
        products={"A": {"arrival": "Exponential~0.2", "route": 0, "PT": 4},
                  "B": {"arrival": "Exponential~0.2", "route": 1, "PT": 3}},
        seed=SEED),
    "Serial line, breakdowns + setup + shifts": lambda: serial_line(
        arrival="Exponential~0.7",
        stages=[Stage("Triangular~0.5~0.7~1.0", ttf="ExponentialMean~120", ttr="ExponentialMean~10", basis="busy"),
                Stage("Triangular~0.6~0.8~1.1", buffer=5, setup=0.5),
                Stage("Normal~0.7~0.1", buffer=5, shifts="Mon-Sun 00:00-24:00")],
        seed=SEED),
    "Order release from a table (no warm-up)": lambda: order_release_line(
        orders={"Time": [0, 50, 100], "Name": ["A", "B", "C"], "Q": [20, 10, 30], "PT": [3, 4, 1]},
        stages=[Stage("PT"), Stage(2, buffer=5)], seed=SEED),
}


def main(until: float = 10_000, warmup: float = 1_000) -> None:
    for title, build in CASES.items():
        no_warmup = "no warm-up" in title
        result = build().run(until, warmup=None if no_warmup else warmup)
        stations = {name: e["utilization"] for name, e in result["elements"].items() if "utilization" in e}
        busy = ", ".join(f"{name} {u:.0%}" for name, u in stations.items())
        print(f"{title:42s} completed {result['completed']:6.0f}  throughput {result['throughput']:.3f}  [{busy}]")


if __name__ == "__main__":
    main()
