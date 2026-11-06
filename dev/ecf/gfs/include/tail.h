# Development retrospectives: the task that has NEXT_FAMILY edited starts the family
# of the next cycle (named by its PDYCYC) once it ends
if [ -n "%NEXT_FAMILY:%" ]; then
  suite_name=$(ecflow_client --query variable ${ECF_NAME}:SUITE)
  next_family=/${suite_name}/primary/%NEXT_FAMILY:%
  next_outputdir=$(ecflow_client --query variable /${suite_name}/primary:OUTPUTDIR)/%NEXT_FAMILY:%
  mkdir -p ${next_outputdir}
  for run in gfs gdas enkfgdas; do
    ecflow_client --alter add variable OUTPUTDIR ${next_outputdir} ${next_family}/${run}
  done
  ecflow_client --resume ${next_family}
fi

timeout 300 ecflow_client --complete  # Notify ecFlow of a normal end
trap 0                    # Remove all traps
exit 0                    # End the shell
