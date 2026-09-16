#!/bin/bash

FAILED_BUNDLES="validation/failed_bundles.txt"

# empty it first so grep below never reads a previous run's result
: > "$FAILED_BUNDLES"

# validation/<dir>/<basename>.val.<xml|json>.<log|html>
#   -> output/<dir>/<basename>.fhir.<xml|json>
grep -rliE "failure|exception" validation/* \
    | sed -E -e 's#^validation/#output/#' -e 's#\.val\.(xml|json)\.(log|html)$#.fhir.\1#' \
    | sort -u > "$FAILED_BUNDLES"

if [[ -s "$FAILED_BUNDLES" ]]; then
    echo -e "'FAILURE' and/or 'exception' could be found for the following FHIR bundles:"
    cat "$FAILED_BUNDLES"
    exit 20
else
    echo -e "No 'FAILURE' and/or 'exception' could be found in validation log files."
    exit 0
fi
