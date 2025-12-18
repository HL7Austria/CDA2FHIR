#!/bin/bash

(grep -r "FAILURE" validation/* > final_validation_check.log)
RESULT="$?"
if [[ "$RESULT" != "0" ]]; then
    echo -e "No FAILURE could be found in validation log files."
    exit 0
else
    echo -e "FAILURE could be found in validation log files."
    exit 20
fi
