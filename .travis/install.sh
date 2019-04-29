#!/bin/bash
set -ev

if [[ ${WOMBAT_TEST} = "no" ]]; then
    pip install --upgrade pip setuptools
    python setup.py -q install
    pip install -r extra_requirements.txt
    pip install coverage pytest-cov coveralls
    pip install codecov

    if [[ ${WR_TEST} = "yes" ]]; then
        git clone https://github.com/webrecorder/webrecorder-tests.git
        cd webrecorder-tests
        pip install --upgrade -r requirements.txt
        ./bootstrap.sh
        cd ..
    fi
else
    cd wombat
    ./boostrap.sh
    cd ..
fi

