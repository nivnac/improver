#!/usr/bin/env bats
# -----------------------------------------------------------------------------
# (C) British Crown Copyright 2017 Met Office.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

@test "percentiles-to-probabilities -h" {
  run improver percentiles-to-probabilities -h
  [[ "$status" -eq 0 ]]
  read -d '' expected <<'__HELP__' || true
usage: improver-percentiles-to-probabilities [-h] [--new_name NEW_NAME]
                                             PERCENTILES_FILE THRESHOLD_FILE
                                             OUTPUT_FILE

Calculate probability from a percentiled field at a 2D threshold level. Eg for
2D percentile levels at different heights, calculate probability that height
is at ground level, where the threshold file contains a 2D topography field.

positional arguments:
  PERCENTILES_FILE     A path to an input NetCDF file containing a percentiled
                       field
  THRESHOLD_FILE       A path to an input NetCDF file containing a threshold
                       value at which probabilities should be calculated.
  OUTPUT_FILE          The output path for the processed NetCDF

optional arguments:
  -h, --help           show this help message and exit
  --new_name NEW_NAME  Name for data in output cube. Defaults to
                       'probability_of_X', where X is the percentiles cube
                       data name
__HELP__
  [[ "$output" == "$expected" ]]
}
