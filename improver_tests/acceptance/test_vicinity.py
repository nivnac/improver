# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# (C) British Crown copyright. The Met Office.
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
"""Tests for the vicinity CLI"""

import pytest

from . import acceptance as acc

pytestmark = [pytest.mark.acc, acc.skip_if_kgo_missing]
CLI = acc.cli_name_with_dashes(__file__)
run_cli = acc.run_cli(CLI)


@pytest.mark.parametrize("vicinity", ("10000", "50000"))
def test_basic(tmp_path, vicinity):
    """Test application with single radii, two values"""
    kgo_dir = acc.kgo_root() / "vicinity"
    kgo_path = kgo_dir / f"kgo_{vicinity}.nc"
    input_path = kgo_dir / "lightning.nc"
    output_path = tmp_path / "output.nc"
    args = [
        input_path,
        vicinity,
        "--output",
        f"{output_path}",
    ]

    run_cli(args)
    acc.compare(output_path, kgo_path)


def test_multiple_vicinities(tmp_path):
    """Test application with two vicinity radii provided simultaneously"""
    kgo_dir = acc.kgo_root() / "vicinity"
    kgo_path = kgo_dir / "kgo_multiple_radii.nc"
    input_path = kgo_dir / "lightning.nc"
    output_path = tmp_path / "output.nc"
    args = [
        input_path,
        "10000,20000",
        "--output",
        f"{output_path}",
    ]

    run_cli(args)
    acc.compare(output_path, kgo_path)
