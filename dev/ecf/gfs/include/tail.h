# Development retrospectives: the task that has NEXT_CYC edited hands the next cycle
# family its date (this cycle plus 6 hours) and starts it
if [ -n "%NEXT_CYC:%" ]; then
  suite_name=$(ecflow_client --query variable ${ECF_NAME}:SUITE)
  next_family=/${suite_name}/primary/%NEXT_CYC:%
  next_pdycyc=$(date -u -d "${PDY} ${cyc}:00 UTC 6 hours" +%%Y%%m%%d%%H)
  next_outputdir=%OUTPUTDIR%/${next_pdycyc}
  mkdir -p ${next_outputdir}
  ecflow_client --suspend ${next_family}
  ecflow_client --alter change variable PDYCYC ${next_pdycyc} ${next_family}
  ecflow_client --alter change label PDYCYC ${next_pdycyc} ${next_family}
  for run in gfs gdas enkfgdas; do
    ecflow_client --alter add variable OUTPUTDIR ${next_outputdir} ${next_family}/${run}
    ecflow_client --requeue=force ${next_family}/${run}
  done
  ecflow_client --resume ${next_family}
fi

timeout 300 ecflow_client --complete  # Notify ecFlow of a normal end
trap 0                    # Remove all traps
exit 0                    # End the shell
