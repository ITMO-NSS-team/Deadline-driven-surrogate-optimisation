import random

from src.noice_experiments.model import SWANParams


def calculate_objectives(model, pop):
    '''
    Calculate two error functions i.e. |model_out - observation| ^ 2
    :param model: Class that can generate SWAN-like output for a given params
    :param pop: Population of SWAN-params i.e. individuals
    '''

    for p in pop:
        params = p.genotype
        closest = model.closest_params(params)
        params.update(drf=closest[0], cfw=closest[1], stpm=closest[2])
        obj_station1, obj_station2, obj_station3 = model.output(params=params)
        p.objectives = (obj_station1, obj_station2, obj_station3)


def crossover(p1, p2, rate):
    if random.random() >= rate:
        return p1

    child_params = SWANParams(drf=(p1.drf + p2.drf) / 2.0,
                              cfw=(p1.cfw + p2.cfw) / 2.0,
                              stpm=(p1.stpm + p2.stpm) / 2.0)
    return child_params


def mutation(individ, rate):
    params = ['drf', 'cfw', 'stpm']
    if random.random() >= rate:
        param_to_mutate = params[random.randint(0, 2)]

        sign = 1 if random.random() < 0.5 else -1
        if param_to_mutate is 'drf':
            individ.drf += sign * 0.3
        if param_to_mutate is 'cfw':
            individ.cfw += sign * 0.05
        if param_to_mutate is 'stpm':
            individ.stpm += sign * 0.001
    return individ
