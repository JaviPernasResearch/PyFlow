from abc import ABC, abstractmethod
from typing import Union
from scipy import stats
from ..Items.item import Item

class DelayStrategy(ABC):
    @abstractmethod
    def get_delay(self, the_item: Item) -> float:
        pass

class RandomDelayStrategy(DelayStrategy):
    """
    A delay strategy that generates a random delay based on a probability distribution.

    Attributes:
        random_times (Union[stats.rv_continuous, stats.rv_discrete]): 
            A random variable representing the delay distribution. 
            This can be a continuous or discrete distribution from the scipy.stats module.

    Methods:
        get_delay(the_item: Item) -> float:
            Generates a random delay value based on the defined distribution.
    """
    def __init__(self, random_times: Union[stats.rv_continuous, stats.rv_discrete, float]):
        if isinstance(random_times, int):
            random_times = stats.uniform(loc=random_times , scale=0)
        self.random_times = random_times

    def get_delay(self, the_item: Item) -> float:
        """
        Generate a random delay value.

        Args:
            the_item (Item): 
                The item for which the delay is being calculated. 
                (Not used in this strategy but included for consistency with the base class).

        Returns:
            float: A random delay value generated from the distribution.
        """
        
        return self.random_times.rvs()

# class LabelDelayStrategy(DelayStrategy):
#     """
#     A delay strategy that calculates the delay based on a specific label value of an item.

#     Attributes:
#         label_name (str): 
#             The name of the label whose value will be used to compute the delay.

#     Methods:
#         get_delay(the_item: Item) -> float:
#             Retrieves the value of the specified label from the item and returns it as the delay.
#     """
#     def __init__(self, label_name: str):
#         self.label_name = label_name

#     def get_delay(self, the_item: Item) -> float:
#         """
#         Calculate the delay based on the value of the specified label.

#         Args:
#             the_item (Item): 
#                 The item for which the delay is being calculated.

#         Returns:
#             float: The value of the specified label, converted to a float, used as the delay.
#         """
#         return float(the_item.get_label_value(self.label_name))

    
class ExpressionDelayStrategy(DelayStrategy):
    """
    A delay strategy that calculates the delay by evaluating a custom Python expression.

    This strategy allows defining complex delay calculations based on multiple item labels.
    The expression is evaluated dynamically, with access to the item object for label values.

    Attributes:
        expression (str): 
            The Python expression to evaluate for calculating the delay.
            The expression can include calls to "item.get_label_value('label_name')" to access item labels.

    Methods:
        get_delay(the_item: Item) -> float:
            Evaluates the expression with the provided item and calculates the delay.
    """
    def __init__(self, expression: str):
        self.expression = expression

    def get_delay(self, the_item: Item) -> float:
        """
        Evaluate the delay based on the given expression and the_item.
        Args:
            the_item (Item): The item to evaluate the expression on.
        Returns:
            float: The computed delay.
        """
        # Provide the_item in the context for the eval function
        context = {"item": the_item}
        try:
            return float(eval(self.expression, {}, context))
        except Exception as e:
            raise ValueError(f"Error evaluating expression '{self.expression}': {e}")