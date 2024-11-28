from typing import Any, List

class DoubleMinBinaryHeat:
    def __init__(self, capacity:int)->None:
        self.values:List[float]=[]
        self.objects:List[Any]=[]

    def swap(self,i:int,j:int)->None:
        interm_val:float=self.values[i]
        self.values[i]= self.values[j]
        self.values[j]=interm_val

        interm_obj:Any=self.objects[i]
        self.objects[i]= self.objects[j]
        self.objects[j]=interm_obj
        #Técnicamente a función swap intercambia os valores e objectos con índices i e j.

    def reset(self)->None:
        self.values.clear()
        self.objects.clear()

    def get_min_value(self)->float:
        if not self.values:
            return float('inf')
        return self.values[0]
    
    def count(self)->int:
        return len(self.values)
    
    def add(self, key:float, content:Any)->None:
        self.values.append(key)
        self.objects.append(content)
        #Añade un novo valor e objeto, mantendo as propiedades.

        child:int=len(self.values) -1
        if child == 0:
            return
        
        parent:int= (child -1)//2

        while key < self.values[parent]:
            self.swap(child, parent)
            child=parent
            if child ==0:
                return
            parent=(child -1)//2

    def first(self)->Any:
        return self.objects[0]
        
    def retrieve_first(self)->Any:
        if not self.values:
            return None
        n:int=len(self.objects)-1
        first:Any=self.objects[0]

        self.objects[0]=self.objects[n]
        self.values[0]=self.values[n]
        self.objects.pop()
        self.values.pop()
            
        i:int=0

        keep:bool=True

        while keep:
            i1:int=2*i+1
            i2:int=2*i+2
            if i1>= n:
                keep=False

            elif i2>=n:
                if self.values[i1]<self.values[i]:
                    self.swap(i1,i)
                    keep=False
            else:
                if self.values[i1] < self.values[i2]:
                    if self.values[i1]<self.values[i]:
                        self.swap(i1,i)
                        i=i1
                    elif self.values[i2]<self.values[i]:
                        self.swap(i2,1)
                        i=i2
                    else:
                        keep=False

                else:
                    if self.values[i2]<self.values[i]:
                        self.swap(i2,i)
                        i=i2
                    elif self.values[i1]<self.values[i]:
                        self.swap(i1,i)
                        i=i1
                    else:
                        keep=False

        return first
                            




