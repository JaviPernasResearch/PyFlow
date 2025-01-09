class Item:
    ITEM_NUMBER:int=0

    def __init__(self, creation_time:float):
        Item.ITEM_NUMBER +=1
        self.creation_time:float=creation_time
        self.type:float=0
        self.input_id=None

    def set_type(self,type:int)->None:
        self.type=type

    def get_creation_time(self)->float:
        return self.creation_time
    
    def get_type(self)->int:
        return self.type

    def set_constrained_input(self, input_id:int):
        self.input_id=input_id

    def get_input_id(self):
        return self.input_id
