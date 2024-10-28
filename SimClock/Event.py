#No código original, Event é unha interfaz de C#, pero en Python
#Non existe o mesmo concepto de interfaces que n C#, podemos empregar
#unha clase base ou definir métodos que sexan implementados polas 
#clases que desexen ser eventos.


from typing import Protocol, List

class Event(Protocol):
    def  execute(self) ->None:
        raise NotImplementedError ('Subclasses must implement this method.')