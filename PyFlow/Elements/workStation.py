from abc import ABC, abstractmethod

class WorkStation(ABC):

    @abstractmethod
    def complete_server_process(self,the_process):
        pass

    @abstractmethod
    def get_name(self):
        pass
