#Import PyFlow Library
from PyFlow import *
#Import stats from scipy if you want to use a distribution for delays
from scipy import stats

def main_template_model():
    # Create the simulation clock
    clock = SimClock.get_instance()

    # Create the elements of the simulation
    arrival_distribution = stats.expon(scale=1)
    source = InterArrivalSource("Source", clock, arrival_distribution)
    buffer = ItemsQueue(100, "Queue", clock)
    process_distribution = stats.expon(scale=2)
    processor = MultiServer(1, process_distribution, "Processor", clock)
    sink = Sink("Sink", clock)

    # Connect the elements
    source.connect([buffer])
    buffer.connect([processor])
    processor.connect([sink])

    # Initialize the simulation
    clock.initialize()

    # Run the simulation for a specified amount of time
    max_sim_time = 10000
    clock.advance_clock(max_sim_time)

    # Output statistics from the simulation
    print(f"Simulation Completed!")
    print(f"Simulation Time: {clock.get_simulation_time()}")
    print(f"Items processed: {sink.get_stats_collector().get_var_input_value()}") 
    avg_waiting_time = buffer.get_stats_collector().get_var_staytime_average()
    print(f"Average Waiting Time: {avg_waiting_time}")

if __name__ == "__main__":
    main_template_model()