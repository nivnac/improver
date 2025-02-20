# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# (C) British Crown Copyright 2017-2021 Met Office.
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
"""Unit tests for the nbhood.NeighbourhoodProcessing plugin."""


import unittest

import numpy as np
from iris.cube import Cube
from iris.tests import IrisTest

from improver.nbhood.nbhood import GeneratePercentilesFromANeighbourhood as NBHood
from improver.synthetic_data.set_up_test_cubes import set_up_probability_cube


class Test__init__(IrisTest):

    """Test the __init__ method of NeighbourhoodProcessing"""

    def test_neighbourhood_method_exists(self):
        """
        Test that no exception is raised if the requested neighbourhood method
        exists.
        """
        neighbourhood_method = "circular"
        radii = 10000
        NBHood(neighbourhood_method, radii)

    def test_neighbourhood_method_does_not_exist(self):
        """
        Test that desired error message is raised, if the neighbourhood method
        does not exist.
        """
        neighbourhood_method = "nonsense"
        radii = 10000
        msg = "The neighbourhood_method requested: "
        with self.assertRaisesRegex(KeyError, msg):
            NBHood(neighbourhood_method, radii)


class Test_process(IrisTest):

    """Test the process method."""

    def setUp(self):
        """Set up a cube."""
        data = np.ones((1, 5, 5), dtype=np.float32)
        data[0, 2, 2] = 0
        self.cube = set_up_probability_cube(
            data,
            thresholds=np.array([278], dtype=np.float32),
            spatial_grid="equalarea",
        )

    def test_default_percentiles(self):
        """Test that the circular neighbourhood processing is successful, if
        the default percentiles are used."""
        neighbourhood_method = "circular"
        radii = 4000
        result = NBHood(neighbourhood_method, radii)(self.cube)
        self.assertIsInstance(result, Cube)

    def test_define_percentiles(self):
        """Test that the circular neighbourhood processing is successful, if
        the percentiles are passed in as a keyword argument."""
        neighbourhood_method = "circular"
        radii = 4000
        percentiles = (0, 25, 50, 75, 100)
        result = NBHood(neighbourhood_method, radii, percentiles=percentiles)(self.cube)
        self.assertIsInstance(result, Cube)


if __name__ == "__main__":
    unittest.main()
