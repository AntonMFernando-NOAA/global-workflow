# Cycled suites reuse one family for every cycle of an hour.  Hand the date and
# the log directory of the next cycle to the next cycle family, then requeue it
# for its next pass.  The first task that ends once that family is complete does
# the hand-over; the tasks that end later find it done and skip it.
_next_name="%NEXT_FAMILY:%"
if [[ -n "${_next_name}" ]]; then
  _next_family="/%SUITE%/${_next_name}"
  _pdy=%PDY:%
  _cyc=%CYC:%
  # The doubled percent signs keep ecFlow from reading the date format as variables
  _next_cycle=$(date --utc --date="${_pdy} ${_cyc}:00 UTC + %ASSIM_FREQ:% hours" +%%Y%%m%%d%%H)
  # The last cycle has no next cycle to prepare
  if [[ "${_next_cycle}" -le "%EDATE:%" ]]; then
    _next_pdy="${_next_cycle:0:8}"
    if [[ "$(ecflow_client --query variable "${_next_family}:PDY")" != "${_next_pdy}" &&
          "$(ecflow_client --query state "${_next_family}")" == "complete" ]]; then
      ecflow_client --alter add variable PDY "${_next_pdy}" "${_next_family}"
      ecflow_client --alter add variable LOGDIR "%LOGROOT:%/${_next_cycle}" "${_next_family}"
      ecflow_client --requeue=force "${_next_family}"
    fi
  fi
fi
