import sys
from os.path import dirname as d
from os.path import abspath, join

# Add rootdir so that tests can import paulobot when pytest
# is run via executable
root_dir = d(abspath(__file__))
sys.path.append(root_dir)