# Deadline-driven-surrogate-optimisation
Here you can find the source code of the algorithms for deadline-driven calibration, described in this [paper](https://dl.acm.org/citation.cfm?id=3326876). 
Our code helps to calibrate complex environmental models. This multi-fidelity approach is helpful in cases when high computational cost of simulations is unacceptable (e.g. in need of fast reaction on natural accidents consequences) or when precise and fast forecast is needed (e.g.in rescue operations).
## More
Suggested algorithm provides deadline-driven approach for surrogate-assisted model calibration, which helps to dynamically adjust a model, trying to ensure better fitness approximation.
In order to reduce time expenses in calibration of environmental models with the presence of time and quality restrictions, we used the following list of algorithms and models:
* surrogate-assisted evolutionary algorithms (SaEA) with variable fidelity
* the third-generation wind wave model Simulating WAves Nearshore (SWAN)
* the Strength Pareto Evolutionary Algorithm (SPEA2)

Advantages of proposed approach:
* the overall optimisation  time has been reduced due to the surrogate modelling(approved by comparison with the baseline evolutionary calibration approach)
* optimisation quality in the presence  of strict deadline has been additionally increased (compared with the preliminary meta-optimisation approach)
## Future Work
The computational overhead for the model runs for meta-optimisation in the preliminary stage can be unacceptable in some real-world scenarios.

How-to-use instructions will be added later.
