#!/bin/bash

VALIDATION_DIR="validation"
OUTPUT_DIR="output"
MATCHED_LINES="final_validation_check.log"
MATCHED_LOGS="failed_validation_logs.txt"
FAILED_BUNDLES="failed_bundles.txt"

# start from a clean state so a re-run never reports stale results
: > "$MATCHED_LOGS"
: > "$FAILED_BUNDLES"

grep -rHiE "failure|exception" "$VALIDATION_DIR"/* > "$MATCHED_LINES"
RESULT="$?"
if [[ "$RESULT" != "0" ]]; then
    echo -e "No 'FAILURE' and/or 'exception' could be found in validation log files."
    exit 0
else
    grep -rliE "failure|exception" "$VALIDATION_DIR"/* > "$MATCHED_LOGS"

    # validation/<dir>/<basename>.val.<xml|json>.<log|html>
    #   -> output/<dir>/<basename>.fhir.<xml|json>
    sed -E \
        -e "s#^${VALIDATION_DIR}/#${OUTPUT_DIR}/#" \
        -e 's#\.val\.(xml|json)\.(log|html)$#.fhir.\1#' \
        "$MATCHED_LOGS" | sort -u > "$FAILED_BUNDLES"

    echo -e "'FAILURE' and/or 'exception' could be found in the following validation log files:"
    cat "$MATCHED_LOGS"
    echo -e "\nAffected FHIR bundles (written to ${FAILED_BUNDLES}):"
    cat "$FAILED_BUNDLES"
    exit 20
fi
