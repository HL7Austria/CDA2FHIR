#!/bin/bash

grep -riE "failure|exception" validation/* > final_validation_check.log
RESULT="$?"
if [[ "$RESULT" != "0" ]]; then
    echo -e "No 'FAILURE' and/or 'exception' could be found in validation log files."
    exit 0
else
    echo -e "'FAILURE' and/or 'exception' could be found in the following validation log files:"
    grep -riEl "failure|exception" validation/*
    exit 20
fi
