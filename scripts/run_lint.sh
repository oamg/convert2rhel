#!/usr/bin/env bash

fail_on_fatal_or_error_only() {
  # We care about fatal (1) and error (2) messages only.
  # The exit code is a sum of numbers corresponding to the message severity level.
  # E.g. if there are both error (2) and warning (4) messages, the exit code is 6.
  local exit_code=0
  pylint --rcfile=.pylintrc "$@" convert2rhel/ || exit_code=$?
  if ! [ $((exit_code & 3)) -eq 0 ]; then
    return $exit_code;
  fi;
  return 0;
}
fail_on_fatal_or_error_only "$@"
