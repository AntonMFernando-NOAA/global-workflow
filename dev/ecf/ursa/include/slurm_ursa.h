#!/bin/bash
#SBATCH --job-name=%RUN%_%TASK%_%CYC%
#SBATCH --account=%ACCOUNT%
#SBATCH --partition=%QUEUE%
#SBATCH --time=%WALLTIME%
#SBATCH --nodes=%NODES%
#SBATCH --ntasks-per-node=%NTASKS%
#SBATCH --cpus-per-task=%CPUS_PER_TASK%
#SBATCH --output=%ECF_JOBOUT%
#SBATCH --export=NONE
