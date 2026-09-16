module load ecflow 2> /dev/null || true
timeout 300 ecflow_client --complete
trap 0
exit 0
