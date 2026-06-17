# C96 dev override: re-pin ECF_HOST and ECF_PORT in case the job's body
# loaded prod_envir again and clobbered them.
unset ECF_HOSTFILE
export ECF_HOST=%ECF_LOGHOST%
export ECF_PORT=%ECF_PORT%

timeout 300 ecflow_client --complete  # Notify ecFlow of a normal end
trap 0                    # Remove all traps
exit 0                    # End the shell
