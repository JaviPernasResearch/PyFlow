import sys
import os
import json
sys.path.insert(0, os.path.dirname(__file__))

from PyFlow import *
from scipy import stats


# =============================================================================
# Custom elements
# =============================================================================

class TypeCountingSink(Sink):
    """Sink that tracks item counts per type and makespan."""
    def __init__(self, name: str, clock):
        super().__init__(name, clock)
        self.type_counts: dict = {}
        self.makespan: float = 0.0

    def start(self) -> None:
        super().start()
        self.type_counts = {}
        self.makespan = 0.0

    def receive(self, the_item) -> bool:
        item_type = the_item.type if the_item.type else "Unknown"
        self.type_counts[item_type] = self.type_counts.get(item_type, 0) + 1
        self.makespan = self.clock.get_simulation_time()
        return super().receive(the_item)

    def print_type_counts(self):
        print(f"\n--- Completed items by type ---")
        for t, count in sorted(self.type_counts.items()):
            print(f"    {t}: {count} items")
        print(f"    TOTAL: {sum(self.type_counts.values())} items")


class BlockageTrackingServer(MultiServer):
    """MultiServer that counts blockage events (finished item cannot move downstream)."""
    def __init__(self, num_servers, delay_strategy, name, clock):
        super().__init__(num_servers, delay_strategy, name, clock)
        self.blockage_count: int = 0

    def start(self) -> None:
        super().start()
        self.blockage_count = 0

    def complete_server_process(self, the_process) -> None:
        the_item = the_process.get_item()
        self.work_in_progress.remove(the_process)
        if self.get_output().send(the_item):
            self.idle_processes.append(the_process)
            self.current_items -= 1
            self.get_input().notify_available()
        else:
            self.blockage_count += 1
            self.completed.append(the_process)


# =============================================================================
# Reporting helpers
# =============================================================================

def print_element_stats(element, name=None):
    label = name or element.get_name()
    sc = element.get_stats_collector()
    print(f"\n  [{label}]")
    print(f"    Input count   : {sc.get_var_input_value()}")
    print(f"    Output count  : {sc.get_var_output_value()}")
    print(f"    Content (now) : {sc.get_var_content_value()}")
    print(f"    Content (avg) : {round(sc.get_var_content_average(), 4)}")
    print(f"    Content (max) : {sc.get_var_content_max()}")
    print(f"    Staytime (avg): {round(sc.get_var_staytime_average(), 4)}")
    print(f"    Staytime (max): {round(sc.get_var_staytime_max(), 4)}")
    print(f"    Staytime (min): {round(sc.get_var_staytime_min(), 4)}")


def print_processor_stats(processor, sim_time, name=None):
    """Extended stats for a BlockageTrackingServer: adds utilization and blockage count."""
    label = name or processor.get_name()
    sc = processor.get_stats_collector()
    utilization = sc.get_var_content_average()  # = fraction of time busy for a single-server
    print(f"\n  [{label}]")
    print(f"    Input count   : {sc.get_var_input_value()}")
    print(f"    Output count  : {sc.get_var_output_value()}")
    print(f"    Content (now) : {sc.get_var_content_value()}")
    print(f"    Utilization   : {round(utilization * 100, 2)} %")
    print(f"    Blockages     : {processor.blockage_count}")
    print(f"    Staytime (avg): {round(sc.get_var_staytime_average(), 4)}")
    print(f"    Staytime (max): {round(sc.get_var_staytime_max(), 4)}")
    print(f"    Staytime (min): {round(sc.get_var_staytime_min(), 4)}")


def print_report_header(title, sim_time, sink):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")
    print(f"  Simulation time : {sim_time}")
    print(f"  Makespan        : {sink.makespan}")
    print(f"  Completed items : {sink.get_stats_collector().get_var_input_value()}")


# =============================================================================
# Model 1 — Three continuous sources, shared two-stage line
# =============================================================================

def run_model1():
    """
    Three InterArrivalSources (one per type, interarrival=10s each) → dedicated
    buffers (cap=10) → shared Processor1 → Processor2 → Sink.
    Processing times are deterministic and type-dependent:
      Type1: PT1=10, PT2=5  |  Type2: PT1=5, PT2=15  |  Type3: PT1=15, PT2=10
    Runs for 120 simulated seconds.
    """
    SimClock._instance = None
    Item.ITEM_NUMBER = 0
    clock = SimClock.get_instance()

    interarrival = stats.uniform(loc=10, scale=0)

    model_item_1 = Item(0, item_type="Type1", labels={"PT1": "10", "PT2": "5"},  model_item=True)
    model_item_2 = Item(0, item_type="Type2", labels={"PT1": "5",  "PT2": "15"}, model_item=True)
    model_item_3 = Item(0, item_type="Type3", labels={"PT1": "15", "PT2": "10"}, model_item=True)

    source1 = InterArrivalSource("Source1", clock, interarrival, model_item=model_item_1)
    source2 = InterArrivalSource("Source2", clock, interarrival, model_item=model_item_2)
    source3 = InterArrivalSource("Source3", clock, interarrival, model_item=model_item_3)

    buffer1 = ItemsQueue(10, "Buffer1", clock)
    buffer2 = ItemsQueue(10, "Buffer2", clock)
    buffer3 = ItemsQueue(10, "Buffer3", clock)

    processor1 = BlockageTrackingServer(1, "item.get_label_value('PT1')", "Processor1", clock)
    processor2 = BlockageTrackingServer(1, "item.get_label_value('PT2')", "Processor2", clock)

    sink = TypeCountingSink("Sink", clock)

    source1.connect([buffer1])
    source2.connect([buffer2])
    source3.connect([buffer3])
    buffer1.connect([processor1])
    buffer2.connect([processor1])
    buffer3.connect([processor1])
    processor1.connect([processor2])
    processor2.connect([sink])

    clock.initialize()

    max_sim_time = 120
    step = 10
    sim_time = 0
    while sim_time < max_sim_time:
        sim_time += step
        clock.advance_clock(sim_time)

    # --- Report ---
    print_report_header("MODEL 1 — Continuous sources / shared serial line", clock.get_simulation_time(), sink)

    print("\n--- Sources ---")
    print_element_stats(source1)
    print_element_stats(source2)
    print_element_stats(source3)

    print("\n--- Buffers ---")
    print_element_stats(buffer1)
    print_element_stats(buffer2)
    print_element_stats(buffer3)

    print("\n--- Processors ---")
    print_processor_stats(processor1, clock.get_simulation_time())
    print_processor_stats(processor2, clock.get_simulation_time())

    print("\n--- Sink ---")
    print_element_stats(sink)
    sink.print_type_counts()

    print(f"\n{'='*55}\n")


# =============================================================================
# Model 2 — Two typed sources, parallel processors P1/P2, shared bottleneck P3
# =============================================================================

def run_model2():
    """
    Two InterArrivalSources (one per item type, interarrival=20 s each) give a
    combined system arrival rate of 1 item per 10 s. Each source feeds its own
    dedicated processor; both processors converge on a shared Processor3.

    Topology:
        Source1 (Type1, 10 s) ──→ Processor1 (10 s) ─────────────────────┐
                                                                           ├→ Processor3 (12 s) → Sink
        Source2 (Type2, 10 s) ──→ Processor2 (7 s) → Buffer2 (cap=10) ───┘

    All service times are deterministic: P1=10 s, P2=7 s, P3=12 s.
    Processor3 is the bottleneck (arrival rate 1/10 > capacity rate 1/12).
    Runs for 240 simulated seconds.

    MCP-equivalent:
        Two InterArrivalSource specs with uniform(loc=10, scale=0) and
        item_type set; MultiServer specs with uniform distributions;
        FirstAvailable connections. No label_expr or label-based routing needed.
    """
    SimClock._instance = None
    Item.ITEM_NUMBER = 0
    clock = SimClock.get_instance()

    interarrival = stats.uniform(loc=10, scale=0)

    model_item_1 = Item(0, item_type="Type1", model_item=True)
    model_item_2 = Item(0, item_type="Type2", model_item=True)

    source1 = InterArrivalSource("Source1", clock, interarrival, model_item=model_item_1)
    source2 = InterArrivalSource("Source2", clock, interarrival, model_item=model_item_2)

    buffer2   = ItemsQueue(10, "Buffer2", clock)

    processor1 = BlockageTrackingServer(1, stats.uniform(loc=10, scale=0), "Processor1", clock)
    processor2 = BlockageTrackingServer(1, stats.uniform(loc=5,  scale=0), "Processor2", clock)
    processor3 = BlockageTrackingServer(1, stats.uniform(loc=9, scale=0), "Processor3", clock)

    sink = TypeCountingSink("Sink", clock)

    source1.connect([processor1])
    source2.connect([processor2])
    processor1.connect([processor3])
    processor2.connect([buffer2])
    buffer2.connect([processor3])
    processor3.connect([sink])

    clock.initialize()

    max_sim_time = 240
    step = 10
    sim_time = 0
    while sim_time < max_sim_time:
        sim_time += step
        clock.advance_clock(sim_time)

    # --- Report ---
    print_report_header(
        "MODEL 2 — Parallel P1/P2 converging at shared bottleneck P3",
        clock.get_simulation_time(), sink
    )

    print("\n--- Sources ---")
    print_element_stats(source1)
    print_element_stats(source2)

    print("\n--- Processors (parallel stage) ---")
    print_processor_stats(processor1, clock.get_simulation_time())
    print_processor_stats(processor2, clock.get_simulation_time())

    print("\n--- Buffer2 (P2 → P3 intermediate) ---")
    print_element_stats(buffer2)

    print("\n--- Processor3 (shared bottleneck) ---")
    print_processor_stats(processor3, clock.get_simulation_time())

    print("\n--- Sink ---")
    print_element_stats(sink)
    sink.print_type_counts()

    print(f"\n{'='*55}\n")


# =============================================================================
# Model 3 — Stochastic extension of Model 2 (ground-truth reference)
# =============================================================================
#
# Same topology as Model 2, but with STOCHASTIC service-time distributions,
# larger input volume, and a longer horizon. It is built entirely from
# MCP-in-scope element/distribution specs (InterArrivalSource, MultiServer,
# ItemsQueue, Sink; expon/norm/triang distributions) so that an AI agent
# driving the PyFlow MCP server can reproduce it exactly.
#
# Running this model also writes the reference JSON that
# pyflow_mcp/structural_score.py scores agent-built models against — the JSON is
# emitted from the very same SimulationSession.snapshot() code path that the MCP
# describe_model() tool uses, so the reference can never drift from this script.
#
#   Source1 (Type1) --> Processor1 ---------------------------\
#                                                              --> Processor3 --> Sink
#   Source2 (Type2) --> Processor2 --> Buffer2 (cap=10) ------/
#
# Service times (stochastic):
#   P1: norm(loc=10, scale=2)
#   P2: expon(scale=5)
#   P3: triang(c=0.5, loc=7, scale=4)   # mean 9 -> shared bottleneck
# Inter-arrivals (stochastic, higher volume): expon(scale=8) per source.

REFERENCE_JSON_PATH = os.path.join(
    os.path.dirname(__file__), "references", "model3.json"
)


def run_model3():
    """
    Build the stochastic extended-Model-2 reference model from the canonical
    specs in pyflow_mcp.reference_models, run it for a long horizon, write the
    ground-truth reference JSON, and print the per-element report.

    The model definition lives in pyflow_mcp.reference_models.model3_specs()
    (the single source of truth shared with the reference emitter), so this
    script and `python -m pyflow_mcp.reference_models model3` always agree.
    """
    from pyflow_mcp.reference_models import build_session, model3_specs

    # build_session() resets the SimClock singleton and Item.ITEM_NUMBER.
    elements, connections = model3_specs()
    session = build_session(elements, connections)
    session.initialize()

    max_sim_time = 10_000
    step = 500
    sim_time = 0
    while sim_time < max_sim_time:
        sim_time += step
        session.clock.advance_clock(sim_time)

    # --- Emit the reference JSON (single source of truth) ---
    snap = session.snapshot()
    ref = {"elements": snap["elements"], "connections": snap["connections"]}
    os.makedirs(os.path.dirname(REFERENCE_JSON_PATH), exist_ok=True)
    with open(REFERENCE_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(ref, f, indent=2)

    # --- Report ---
    el = session.elements
    sink = el["snk"]
    sim_now = session.clock.get_simulation_time()

    print(f"\n{'='*55}")
    print("  MODEL 3 — Stochastic extension of Model 2 (ground-truth reference)")
    print(f"{'='*55}")
    print(f"  Simulation time : {sim_now}")
    print(f"  Completed items : {sink.get_stats_collector().get_var_input_value()}")

    print("\n--- Sources ---")
    print_element_stats(el["src1"])
    print_element_stats(el["src2"])

    print("\n--- Processors (parallel stage) ---")
    print_processor_stats(el["p1"], sim_now)
    print_processor_stats(el["p2"], sim_now)

    print("\n--- Buffer2 (P2 -> P3 intermediate) ---")
    print_element_stats(el["buf2"])

    print("\n--- Processor3 (shared bottleneck) ---")
    print_processor_stats(el["p3"], sim_now)

    print("\n--- Sink ---")
    print_element_stats(sink)
    print(f"\n--- Completed items by type ---")
    for t, count in sorted(sink.type_counts.items()):
        print(f"    {t}: {count} items")
    print(f"    TOTAL: {sum(sink.type_counts.values())} items")

    print(f"\n  Reference JSON written to: {REFERENCE_JSON_PATH}")
    print(f"\n{'='*55}\n")


# =============================================================================
# Entry point — select which model to run
# =============================================================================

if __name__ == "__main__":
    # Change MODEL to 1, 2, or 3 to select which model runs
    MODEL = 1

    if MODEL == 1:
        run_model1()
    elif MODEL == 2:
        run_model2()
    elif MODEL == 3:
        # Stochastic extended-Model-2 reference model; also writes the
        # ground-truth reference JSON to references/model3_stochastic.json.
        run_model3()

