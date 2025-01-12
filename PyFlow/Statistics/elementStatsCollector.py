from ..Elements.element import Element
from .statsCollector import StatisticsCollector
from .statTimeVariable import StatTimeVariable
from .statLevelVariable import StatLevelVariable
from ..SimClock.simClock import SimClock
from ..Items.item import Item


class ElementStatsCollector(StatisticsCollector):
    def __init__(self, element:Element, simclock:SimClock):
        super().__init__(element, simclock)
        self.var_input:StatLevelVariable =  StatLevelVariable()
        self.var_output:StatLevelVariable =  StatLevelVariable()
        self.var_staytime:StatTimeVariable =  StatTimeVariable()
        self.var_content:StatLevelVariable =  StatLevelVariable()

        # Dictionary to store entry time for each item
        self.entry_times = {}
    
    def on_entry(self, the_item:Item):
        # Only considers shipments of 1 item
        self.var_input.update(1)
        self.var_content.update(1)

        current_time = self.simclock.get_simulation_time()
        self.entry_times[the_item] = current_time

    def on_exit(self, the_item:Item):
        # Only considers shipments of 1 item
        self.var_output.update(1)
        self.var_content.update(-1)

        if the_item in self.entry_times:
            entry_time = self.entry_times.pop(the_item)  # Get and remove the entry time
            stay_time = self.simclock.get_simulation_time() - entry_time  # Calculate the stay time
            
            # Update the staytime variable
            self.var_staytime.update(stay_time)

        # Getters for each of the variables
    def get_var_input_stats(self):
        """Retrieve statistics for the input variable."""
        return self.var_input.get_stats()

    def get_var_output_stats(self):
        """Retrieve statistics for the output variable."""
        return self.var_output.get_stats()

    def get_var_staytime_stats(self):
        """Retrieve statistics for the stay time variable."""
        return self.var_staytime.get_stats()

    def get_var_content_stats(self):
        """Retrieve statistics for the content variable."""
        return self.var_content.get_stats()

    def get_var_input_max(self) -> float:
        """Retrieve the max value for the input variable."""
        return self.var_input.get_stats_max()

    def get_var_output_max(self) -> float:
        """Retrieve the max value for the output variable."""
        return self.var_output.get_stats_max()

    def get_var_staytime_max(self) -> float:
        """Retrieve the max value for the stay time variable."""
        return self.var_staytime.get_stats_max()

    def get_var_content_max(self) -> float:
        """Retrieve the max value for the content variable."""
        return self.var_content.get_stats_max()

    def get_var_input_min(self) -> float:
        """Retrieve the min value for the input variable."""
        return self.var_input.get_stats_min()

    def get_var_output_min(self) -> float:
        """Retrieve the min value for the output variable."""
        return self.var_output.get_stats_min()

    def get_var_staytime_min(self) -> float:
        """Retrieve the min value for the stay time variable."""
        return self.var_staytime.get_stats_min()

    def get_var_content_min(self) -> float:
        """Retrieve the min value for the content variable."""
        return self.var_content.get_stats_min()

    def get_var_input_average(self) -> float:
        """Retrieve the average value for the input variable."""
        return self.var_input.get_stats_average()

    def get_var_output_average(self) -> float:
        """Retrieve the average value for the output variable."""
        return self.var_output.get_stats_average()

    def get_var_staytime_average(self) -> float:
        """Retrieve the average value for the stay time variable."""
        return self.var_staytime.get_stats_average()

    def get_var_content_average(self) -> float:
        """Retrieve the average value for the content variable."""
        return self.var_content.get_stats_average()
    
    def get_var_input_value(self) -> float:
        """Retrieve the current value for the input variable."""
        return self.var_input.get_stats_value()

    def get_var_output_value(self) -> float:
        """Retrieve the current value for the output variable."""
        return self.var_output.get_stats_value()

    def get_var_staytime_value(self) -> float:
        """Retrieve the current value for the stay time variable."""
        return self.var_staytime.get_stats_value()

    def get_var_content_value(self) -> float:
        """Retrieve the current value for the content variable."""
        return self.var_content.get_stats_value()