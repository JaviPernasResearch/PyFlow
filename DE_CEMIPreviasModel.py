import math
import os
import pickle
import random
import sys
import time
from typing import Sequence
from itertools import repeat

import numpy
import argparse
import pandas as pd
from scoop import futures
from deap import base, creator, tools, algorithms
import subprocess

from CEMI_Previas_Model_3SCEN import main

def check_dir(directory):
    # Comprobación de que existen los directorios que se usan en todo el código

    if not os.path.exists(directory+"/"):
        os.makedirs(directory+"/")
        
    else:
        pass


# from cosimulate import cosimulate, check

##Params

nb_Previas = 90
directory = 'Results'
F_factor_range = [0.3, 0.6, 0.9]
F_factor_range = [0.3]
cr_prob_range = [0.25, 0.5, 0.75]
cr_prob_range = [0.75]
SAVE_BEST_ITER_TO_EXCEL_ON = 0

#DE Fixed params
pop_size= 50
n_gen = 200
n_best = 1
MAX_TIME = 60 * 30

## Debug Error In Function Function

def validate_chromosome(chromosome):
    """
    Validates that the chromosome contains the numbers 1 to 90 with no duplicates.
    
    Parameters:
        chromosome (list): The list of genes representing the chromosome.
        
    Returns:
        bool: True if chromosome contains numbers 1 to 90 with no duplicates, False otherwise.
    """
    chromosome_set = set(chromosome)  # Convert chromosome list to set to remove duplicates

    # Check if the two sets are identical
    if len(chromosome_set) == 90:
        return True
    else:
        return False

def gen_individual(icls, pcls): #individual/inspection class --> constructors

    genes = []
    #Generate vector of genes
    for i in range(1,90+1):
        genes.append(i)

    genes = icls(genes) #this creates and instance of the Creator.Individual Class
    random.shuffle(genes)     # Shuffle the list to get a random order
    genes.inspection = pcls(random.randint(0, 1) for _ in range(len(genes)))

    ## Initialization for debugging    
    # sol = [42, 35, 18, 80, 50, 60, 83, 32, 78, 30, 2, 48, 78, 51, 17, 14, 37, 47, 44, 78, 70, 45, 27, 58, 24, 11, 31, 21, 6, 75, 16, 13, 86, 55, 67, 40, 70, 15, 53, 36, 73, 34, 4, 43, 84, 34, 28, 5, 38, 77, 2, 71, 32, 20, 44, 7, 69, 89, 23, 64, 76, 81, 49, 79, 10, 56, 63, 27, 62, 54, 24, 8, 74, 20, 7, 13, 68, 57, 46, 22, 29, 6, 19, 9, 41, 85, 74, 9, 12, 61]
    # soli = [0, 1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 1, 1, 1, 1, 1, 0, 1, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 1, 0, 1, 1, 0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 1, 0, 0, 1]
    # for i, g in enumerate(genes):
    #     genes[i] = sol [i]
    #     genes.inspection[i] = soli[i]

    return genes

def send_to_model(individual, sim):
    """
    Formats and sends the individual data to the CEMI_Previas_Model_3SCEN.
    
    Parameters:
        individual: Individual from DE algorithm containing priorities and inspections
        sim: Simulation parameter (not used in this implementation)
    
    Returns:
        tuple: Containing the fitness value (retrasos,)
    """
    # Extract priorities and inspections from individual
    priorities = [g for g in individual]  # Get priorities list (1-90)
    inspections = [i for i in individual.inspection]  # Get inspections list (0s and 1s)
    
    # Send to simulation model and get results
    simTime, output, retrasos, inspecciones = main(priorities, inspections)
    if retrasos == 0:
        print("\nOptimal Solution Found!")
        print("Priorities:", priorities)
        print("Inspections:", inspections)
        print(f"Number of inspections: {sum(inspections)}")
        print("Simulation time:", simTime)  
    # Return delays as fitness value (minimization problem)
    return (retrasos,)

def evaluate(individual, plantOn):
    # mu, k, limit = individual
    # mu *= 2.0
    # individual = mu, k, limit
    return send_to_model(individual, plantOn)
    # return (cosimulate(individual),)

#DE Operators

def de_mutation(base_ind_pop, xr1_pop, xr2_pop, F=1):
    """
    Performs differential evolution mutation with a constraint to maintain a sequence from 1 to 90.

    Parameters:
        base_ind_pop (list of lists): Base individuals.
        xr1_pop (list of lists): First difference vector.
        xr2_pop (list of lists): Second difference vector.
        F (float): Scaling factor for mutation.

    Returns:
        list of lists: Mutated population where the chromosome remains a permutation of 1 to 90.
    """
    l = len(base_ind_pop[0])  # Length of individuals
    for base_ind, xr1, xr2 in zip(base_ind_pop, xr1_pop, xr2_pop):
        for i in range(l):
            # Perform differential evolution mutation
            new_value = base_ind[i] + F * (xr1[i] - xr2[i])
            new_value = round(new_value)  # Ensure new value is an integer

            # Keep new value within valid range (1 to 90)
            if new_value < 1:
                new_value = 1
            elif new_value > 90:
                new_value = 90

            # Swap the value with another gene holding the same value
            if new_value != base_ind[i]:
                # Find the index of another gene with the same value as `new_value`
                duplicate_index = base_ind.index(new_value)
                base_ind[duplicate_index] = base_ind[i]
                base_ind[i] = new_value

    ##Proceed with inspection
            base_ind.inspection[i] = base_ind.inspection[i] + F * (xr1.inspection[i] - xr2.inspection[i])
            base_ind.inspection[i] = round(base_ind.inspection[i])
            if base_ind.inspection[i] < 0:
                base_ind.inspection[i]=0
            if base_ind.inspection[i] >= 1:
                base_ind.inspection[i]=1

    return base_ind_pop

# def set_inspection():
#     def decorator(func):
#         def wrapper(*args, **kargs):
#             mutant = func(*args, **kargs)
#             for i in range(len(mutant[0])):
#                 if mutant[0].inspection[i] < 0:
#                     mutant[0].inspection[i]=-mutant[0].inspection[i]
#                 if mutant[0].inspection[i] >= 1:
#                     mutant[0].inspection[i]=mutant[0].inspection[i]/100

#             return mutant
#         return wrapper
#     return decorator

def binomial_crossover(target_pop, mutant_pop, CR=0.5):
    l = len(target_pop[0])
    for target, mutant in zip(target_pop, mutant_pop):
        # k = random.randint(0, l - 1)
        for i in range(l):
            # if not (random.random() < CR or i == k):
            if not random.random() < CR:
                # mutant[i] = target[i]
                previous_value = mutant[i]
                previous_ivalue = mutant.inspection[i]
                duplicate_index = mutant.index(target[i])
                mutant[i] = target[i]
                mutant.inspection[i] = target.inspection[i]
                mutant[duplicate_index] = previous_value
                mutant.inspection[duplicate_index] = previous_ivalue
    return mutant_pop


def checkBounds(min, max):
    def decorator(func):
        def wrapper(*args, **kargs):
            offspring = func(*args, **kargs)
            for child in offspring:
                for i in range(len(child)):
                    if child[i] > max:
                        child[i] = max
                    elif child[i] < min:
                        child[i] = min
                    else:
                        child[i] = int(round(child[i],0))
            return offspring
        return wrapper
    return decorator

def setup(args):
    # Genetic operators
    if args.de:
        toolbox.register("select", tools.selRandom, k=3 * pop_size)
        toolbox.register("mutate", de_mutation, F=F_factor)
        # toolbox.decorate("mutate", checkBounds(1, nb_Previas))
        toolbox.register("mate", binomial_crossover, CR=cr_prob)
        # toolbox.decorate("mate", checkBounds(1, nb_Previas))
        algorithm = de
    else:
        parser.print_help(sys.stderr)
        sys.exit(1)

    # To parallelize the evaluation using Scoop
    # toolbox.register("map", futures.map)

    # Random seed
    random.seed(int(time.time()))

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
    best = tools.HallOfFame(maxsize=1)

    return algorithm, population, toolbox, stats, logbook, best

def de(population, toolbox, statss, logbbok, best):

    start_time = time.time()
    last_logging_time = start_time #save best value every second

    # Evaluate initial population
    fitnesses =list(map(lambda ind: toolbox.evaluate(ind, sim), population)) ## applies the toolbox.evaluate function to each individual in the pop population and calculates the fitness values
    # fitnesses = toolbox.map(toolbox.evaluate, population)
    for ind, fit in zip(population, fitnesses):
        ind.fitness.values = fit

    # Update best individual
    best.update(population)

    # Update logs
    record = stats.compile(population)
    logbook.record(gen=0, nevals=len(population), **record)
    logbook_ind.record(gen=0, bestind= best.items[0], fitness= best[0].fitness.values[0])
    logbook_ind_time.record(time=0, bestind= best.items[0], fitness= best[0].fitness.values[0])

    print(logbook.stream)    

    # Begin the generational process
    for gen in range(1, n_gen):
        # Selection        
        selected = toolbox.select(population)
        l = len(selected)
        base_ind = selected[0 : l // 3]
        xr1 = selected[l // 3 : 2 * l // 3]
        xr2 = selected[2 * l // 3 : l]

        # Mutation
        base_ind = [toolbox.clone(ind) for ind in base_ind]
        mutant = toolbox.mutate(base_ind, xr1, xr2)

        # for m in mutant:
        #     if not validate_chromosome(m):
        #         print("ERROR")
        # for m in base_ind:
        #     if not validate_chromosome(m):
        #         print("ERROR")

        # Crossover
        trial = toolbox.mate(population, mutant)

        # Evaluate new individuals
        fitnesses =list(map(lambda ind: toolbox.evaluate(ind, sim), trial)) ## applies the toolbox.evaluate function to each individual in the pop population and calculates the fitness values
        for ind, fit in zip(trial, fitnesses):
            ind.fitness.values = fit

        # Replace the population
        l = len(population)
        for i in range(l):
            if trial[i].fitness > population[i].fitness:
                population[i] = trial[i]

        # Update the best individual
        best.update(population)

        # Update logs
        record = stats.compile(population)
        logbook.record(gen=gen, nevals=len(population), **record)
        
        current_time = time.time()
        if current_time - last_logging_time >= 1:
            logbook_ind_time.record(time=round(current_time - start_time), bestind=best.items[0], fitness=best[0].fitness.values[0])
            last_logging_time = current_time

        logbook_ind.record(gen=gen, bestind= best.items[0], fitness= best[0].fitness.values[0])

        print(logbook.stream)

        elapsed_time = time.time() - start_time
        if elapsed_time >= MAX_TIME or best[0].fitness.values[0]==0:
           break
    
    
    # ##Terminate simulation
    # sim.quit()

    return best#, g, elapsed_time

def save_data():
    
    logbook_ind.record(fitness=best[0].fitness.values[0],ind=best.items[0])

    file_name= 'Logbook_DE' + '_S' + str(pop_size)+ '_CR' + str(cr_prob)+ '_F' + str(F_factor)+ '_iter'+ str(iter)

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

# Genes, chromosomes, and population
creator.create("FitnessMin", base.Fitness, weights=(-1.0,)) #A minimizing fitness is built using negatives weights, while a maximizing fitness has positive weights.
creator.create("Individual", list, fitness=creator.FitnessMin, inspection = None)
creator.create("Inspection", list)

##Base Registers
toolbox = base.Toolbox()
toolbox.register("individual", gen_individual, creator.Individual, creator.Inspection)
toolbox.register("population", tools.initRepeat, list, toolbox.individual)
toolbox.register("evaluate", evaluate)

if __name__ == "__main__":

    sim = None
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ga",
        action="store_true",
        help="Genetic algorithm with tournament selection, BLX-\u03B1 crossover and Gaussian mutation",
    )
    parser.add_argument("--de", action="store_true", help="Differential Evolution")
    args = parser.parse_args()
    args.de = True

    ## Initialize Params
    # df=pd.read_csv(str(os.getcwd()).replace('\\', '/')+"/train.csv", sep=",")

    try:
        check_dir(directory)
        for F_factor in F_factor_range:
            for cr_prob in cr_prob_range:
                for iter in range(1):
                # Run algorithm
                    logbook_ind_time = tools.Logbook()
                    logbook_ind = tools.Logbook()
                    
                    # Init execution
                    algorithm, population, toolbox, stats, logbook, best = setup(args)
                    best = algorithm(population, toolbox, stats, logbook, best)

                    if SAVE_BEST_ITER_TO_EXCEL_ON:
                        dfRes = pd.DataFrame(columns=["Prio", "Ins"])
                        for i, g in enumerate(best.items[0]):
                            dfRes.loc[i] = [
                            g,
                            best.items[0].inspection[i]
                        ]
                        dfRes.to_excel(directory + f"//DE_Previas_SOL__{iter}.xlsx", sheet_name="S1")

                    save_data()
    finally:
    # Ensure the external app is closed
        if sim:
            sim.quit()