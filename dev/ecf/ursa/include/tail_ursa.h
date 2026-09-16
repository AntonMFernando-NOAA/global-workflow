# Save ECF_* before module load which resets them
_ecf_host="${ECF_HOST}"
_ecf_port="${ECF_PORT}"
module load ecflow 2> /dev/null || true
export ECF_HOST="${_ecf_host}"
export ECF_PORT="${_ecf_port}"
timeout 300 ecflow_client --complete
trap 0
exit 0
