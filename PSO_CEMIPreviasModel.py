import pandas as pd
import matplotlib.pyplot as plt

from scoop import futures
from deap import base, creator, tools, algorithms
from typing import Sequence
from itertools import repeat

import pickle
import sys
import subprocess
import operator
import random
import math
import time
import os
import csv
import argparse
import numpy

from CEMIPreviasModel import main

# Params
nb_previas=90
directory='Results'
pso_acce_range=[1, 1.496, 2]
pso_inertia_range=[0.5, 0.7298, 0.8]
#elitism_ON=True
pseudo_search_ON=False

# PSO Fixed params
pop_size=50
n_gen=200
n_best=1 # Para elitismo
MAX_TIME=60*30
SAVE_BEST_ITER_TO_EXCEL_ON=False

def check_dir(directory):
    # Comprobación de que existen los directorios que se usan en todo el código

    if not os.path.exists(directory+"/"):
        os.makedirs(directory+"/")

    else:
        pass

def send_to_model(data_to_send, sim):
    # Se realiza toda la conexión con PS, se inicializa, se transforma la información en el formato DataFrame y se escribe en la tabla MBOM_Python,
    # se inicia la simulación y se deja dos segundos ejecutando para darle tiempo para obtener los resultados
    # Se lee el resultado del número de previas retrasadas y se corta la comunicación

    #priorities = [g for g in individual]  # Assuming first list is priorities (1-90)
    #inspection = [i for i in individual.inspection]# Assuming second list is inspection (0s and 1s)

    # data_2=pd.DataFrame(individual, columns=["Inspeccion", "Prioridad"])
    data_2 = pd.DataFrame(data_to_send, columns=["Inspeccion", "Prioridad"])
    inspeccion_list = data_2["Inspeccion"].tolist()
    prioridad_list = data_2["Prioridad"].tolist()

    retrasos, inspecciones = main(prioridad_list, inspeccion_list)

    # retrasos=sim.get_value(object_name=".Models.Model.nPrevias_Retrasadas") 
    # inspecciones=sim.get_value(object_name=".Models.Model.n_Inspecciones") 

    # return (inspecciones-retrasos*6,)
    if pseudo_search_ON:
        return (inspecciones-retrasos*6, )
    else:
        return (retrasos,)

def generate_order_inspection(input, flag_out=False):

    counter_insp=0
    inspection_list=[]
    numeros_unicos = set()
    ID_list=[]

    numeros_unicos.add(0)
    numeros_unicos.add(91)
    numeros_unicos.add(92)
    numeros_unicos.add(93)
    numeros_unicos.add(94)
    numeros_unicos.add(95)
    numeros_unicos.add(96)
    numeros_unicos.add(97)
    numeros_unicos.add(98)
    numeros_unicos.add(99)
    numeros_unicos.add(100)

    # Se comprueba que todos los números sean diferentes y si lo son, se les da otro número
    for i in range(len(input)//2):
        n=int(round(input[i], 2)*100)
        
        while n in numeros_unicos:
            n=n+1
            
            if n > len(input)//2:
                n=1

        numeros_unicos.add(n)
        ID_list.append(n)

    for i in range(len(input)//2):
        insp_input=input[i+len(input)//2]

        if insp_input>0.5:
            insp_input=1

        else:
            insp_input=0

        insp=insp_input

        if insp==1:
            counter_insp=counter_insp+1

        ID=int(ID_list[i]*1)
        inspection_list.append([insp, ID])


    return inspection_list, counter_insp

def PSO_PS(individual, sim):
    
    data, n_insp=generate_order_inspection(individual)
    output=send_to_model(data, sim)

    return output

def setup(args):
    # PSO operators
    if args.pso:
        algorithm=pso
    else:
        parser.print_help(sys.stderr)
        sys.exit(1)

    # Statistics
    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("avg", numpy.mean)
    stats.register("std", numpy.std)
    stats.register("min", numpy.min)
    stats.register("max", numpy.max)

    # Logs
    logbook = tools.Logbook()
    logbook.header = ["gen", "nevals"] + stats.fields

    # Generate initial Population randomly
    population = toolbox.population(n=pop_size)

    # Solution
    best = tools.HallOfFame(maxsize=n_best)

    return algorithm, population, toolbox, stats, logbook, best

def gen_particle(size, p_min, p_max, s_min, s_max):
    # Se crean las partículas poniendo un máximo y un mínimo valor de posición
    # size es el número de dimensiones que tiene la particula

    part=creator.Particle(random.uniform(p_min, p_max) for _ in range(size))
    part.speed=[random.uniform(s_min, s_max) for _ in range(size)]
    part.smin=s_min
    part.smax=s_max
    part.pmin=p_min
    part.pmax=p_max
    part.best=part[:]
    return part

def update_particle(part, best, phi_1, phi_2, w):
    # Se crean las posiciones actuales teniendo en cuenta las aceleraciones phi_1 y phi_2
    #print(f"particula:\n{part} // \nbest: {part.best} // \nbest best: {best}")
    for i in range(len(part)):
        e=0
        #print(f"iter: {i} // trozo: {best[0][i]}")
        part.speed[i]=part.speed[i]*w+phi_1*(part.best[i]-part[i])+phi_2*(best[0][i]-part[i])
        part[i]=part[i]+part.speed[i]

        if part[i]>part.pmax:
            part[i]=part.pmax

        if part[i]<part.pmin:
            part[i]=part.pmin
    

def save_data():
    logbook_ind.record(fitness=best[0].fitness.values[0],ind=best.items[0])

    if algorithm == pso:
        file_name= 'Logbook_PSO' + '_PS' + str(pop_size)+ '_Cs' + str(pso_acce)+ '_w' + str(pso_inertia)+ '_iter'+ str(iter)

    full_path = os.path.join(directory, file_name)
    try:
        # Try to create the file (if it doesn't exist)
        with open(full_path, "x") as file:
            pass  # Do nothing if the file is created successfully
    except FileExistsError:
        # File already exists
        pass
    with open(full_path, "wb") as file:
        pickle.dump(logbook, file, protocol=pickle.HIGHEST_PROTOCOL)
        pickle.dump(logbook_ind, file, protocol=pickle.HIGHEST_PROTOCOL)
        # pickle.dump(logbook_pop, file,  protocol=pickle.HIGHEST_PROTOCOL)
        pickle.dump(logbook_ind_time, file,  protocol=pickle.HIGHEST_PROTOCOL)




def pso(population, toolbox, stats, logbook, best):
    # 
    # 
    # 
    
    start_time=time.time()
    last_record_time=start_time

    # Evaluate inital population
    fitnsesses=list(map(lambda ind: toolbox.evaluate(ind, sim), population))
    for ind, fit in zip(population, fitnsesses):
        ind.fitness.values=fit


    best.update(population)
    
    record=stats.compile(population)
    logbook.record(gen=0, nevals=len(population), **record)
    logbook_ind.record(gen=0, bestind=best.items[0], fitness=best[0].fitness.values[0])
    logbook_ind_time.record(time=0, bestind=best.items[0], fitness=best[0].fitness.values[0])
    
    print(logbook.stream)

    # Start the evolution of particles
    for gen in range(1, n_gen):

        offspring=[toolbox.clone(ind) for ind in population if ind != best]

        # Update the positions
        for part in offspring:
            toolbox.update(part, best)

        # Evaluate new individuals:
        fitnsesses=list(map(lambda ind: toolbox.evaluate(ind, sim), offspring))

        for ind, fit in zip(offspring, fitnsesses):
            ind.fitness.values=fit

        offspring.extend(best.items)

        # Replace population
        population[:]=offspring

        # Update the best particle
        best.update(population)

        # Update logs
        record=stats.compile(population)
        logbook.record(gen=gen, nevals=pop_size-n_best, **record)

        current_time=time.time()
        if current_time - last_record_time >= 1:
            logbook_ind_time.record(time=round(current_time - start_time), bestind=best.items[0], fitness=best[0].fitness.values[0])
            last_record_time=current_time
        
        logbook_ind.record(gen=gen, bestind=best.items[0], fitness= best[0].fitness.values[0])

        print(logbook.stream)
        
        elapsed_time = time.time() - start_time

        if elapsed_time >= MAX_TIME or best[0].fitness.values[0]==0:
           break

    return best

# Definitions
creator.create("FitnessMin", base.Fitness, weights=(-1.0,)) # Minimize function
creator.create("Particle", list, fitness=creator.FitnessMin, speed=list, smin=None, smax=None, best=None)



# Registers
toolbox=base.Toolbox()
toolbox.register('particle', gen_particle, size=nb_previas*2, p_min=0, p_max=1, s_min=0, s_max=1)
toolbox.register('population', tools.initRepeat, list, toolbox.particle)
toolbox.register('evaluate', PSO_PS)




if __name__ == "__main__":
    sim=None

    # Parse arguments
    parser=argparse.ArgumentParser()
    parser.add_argument(
        "--pso",
        action="store_true",
        help="PSO with elitism"
    )
    args=parser.parse_args()
    args.pso=True
    pso_acce=1
    pso_inertia=0.5

    try:
        check_dir(directory)
        for pso_acce in pso_acce_range:
            for pso_inertia in pso_inertia_range:
                for iter in range(6):
                    logbook_ind_time=tools.Logbook()
                    logbook_ind=tools.Logbook()
                    toolbox.register("update", update_particle, phi_1=pso_acce, phi_2=pso_acce, w=pso_inertia)

                    # Init execution
                    algorithm, population, toolbox, stats, logbook, best = setup(args)
                    best = algorithm(population, toolbox, stats, logbook, best)

                    if SAVE_BEST_ITER_TO_EXCEL_ON:
                        dfRes = pd.DataFrame(columns=["Prio", "Ins"])
                        for i, g in enumerate(best.items[0]):
                            dfRes.loc[i] = [
                            g,
                            best.items[0][i]
                        ]
                        dfRes.to_excel(directory + f"//PSO_Previas_SOL_{iter}.xlsx", sheet_name="S1")

                    save_data()
    finally:
        if sim:
            sim.quit()

