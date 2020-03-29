#!/bin/bash

if [ -z "$PAULOBOT" ]; then
    # Try and work out the path based on location of this script
    # This assumes this script hasn't been moved out of the repo
    # Note: this might not work in all cases but this only going to be
    # used in the dev phase so good enough
    PAULOBOT="$( cd $( dirname "$0" ) && pwd )"
fi

cd ${PAULOBOT}

echo "Running PauloBot at ${PAULOBOT}"
python3.7 -m paulobot "$@"