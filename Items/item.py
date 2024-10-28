class Item:
    ITEM_NUMER:int=0

    def __init__(self, creation_time:float):
        Item.ITEM_NUMBER +=1
        self.creation_time:float=creation_time
        self.type:float=0

    def set_type(self,type:int)->None:
        self.type=type

    def get_creation_time(self)->float:
        return self.creation_time
    
    def get_type(self)->int:
        return self.type

    
