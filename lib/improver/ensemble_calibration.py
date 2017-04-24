# -*- coding: utf-8 -*-
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
"""
This module defines all the "plugins" specific for ensemble calibration.

"""
import copy
import numpy as np
import random
from scipy import stats
from scipy.optimize import minimize
from scipy.stats import norm
import warnings

import cf_units as unit
import iris

from ensemble_calibration_utilities import (
    convert_cube_data_to_2d, concatenate_cubes, rename_coordinate,
    check_predictor_of_mean_flag)


class ContinuousRankedProbabilityScoreMinimisers(object):
    """
    Minimise the Continuous Ranked Probability Score (CRPS)

    Calculate the optimised coefficients for minimising the CRPS based on
    assuming a particular probability distribution for the phenomenon being
    minimised.

    The number of coefficients that will be optimised depend upon the initial
    guess.

    Minimisation is performed using the Nelder-Mead algorithm for 200
    iterations to limit the computational expense.
    Note that the BFGS algorithm was initially trialled but had a bug
    in comparison to comparative results generated in R.

    """

    # Maximum iterations for minimisation using Nelder-Mead.
    MAX_ITERATIONS = 200

    # The tolerated percentage change for the final iteration when
    # performing the minimisation.
    TOLERATED_PERCENTAGE_CHANGE = 5

    # An arbitrary value set if an infinite value is detected
    # as part of the minimisation.
    BAD_VALUE = np.float64(999999)

    def __init__(self):
        # Dictionary containing the minimisation functions, which will
        # be used, depending upon the distribution, which is requested.
        self.minimisation_dict = {
            "gaussian": self.normal_crps_minimiser,
            "truncated gaussian": self.truncated_normal_crps_minimiser}

    def crps_minimiser_wrapper(
            self, initial_guess, forecast_predictor, truth, forecast_var,
            predictor_of_mean_flag, distribution):
        """
        Function to pass a given minimisation function to the scipy minimize
        function to estimate optimised values for the coefficients.

        Parameters
        ----------
        initial_guess : List
            List of optimised coefficients.
            Order of coefficients is [c, d, a, b].
        forecast_predictor : Iris cube
            Cube containing the fields to be used as the predictor,
            either the ensemble mean or the ensemble members.
        truth : Iris cube
            Cube containing the field, which will be used as truth.
        forecast_var : Iris cube
            Cube containg the field containing the ensemble variance.
        predictor_of_mean_flag : String
            String to specify the input to calculate the calibrated mean.
            Currently the ensemble mean ("mean") and the ensemble members
            ("members") are supported as the predictors.
        distribution : String
            String used to access the appropriate minimisation function
            within self.minimisation_dict.

        Returns
        -------
        optimised_coeffs : List
            List of optimised coefficients.
            Order of coefficients is [c, d, a, b].

        """
        def calculate_percentage_change_in_last_iteration(allvecs):
            """
            Calculate the percentage change that has occurred within
            the last iteration of the minimisation. If the percentage change
            between the last iteration and the last-but-one iteration exceeds
            the threshold, a warning message is printed.

            Parameters
            ----------
            allvecs : List
                List of numpy arrays containing the optimised coefficients,
                after each iteration.
            """
            last_iteration_percentage_change = np.absolute(
                (allvecs[-1] - allvecs[-2]) / allvecs[-2])*100
            if (np.any(last_iteration_percentage_change >
                       self.TOLERATED_PERCENTAGE_CHANGE)):
                np.set_printoptions(suppress=True)
                msg = ("\nThe final iteration resulted in a percentage change "
                       "that is greater than the accepted threshold of 5% "
                       "i.e. {}. "
                       "\nA satisfactory minimisation has not been achieved. "
                       "\nLast iteration: {}, "
                       "\nLast-but-one iteration: {}"
                       "\nAbsolute difference: {}\n").format(
                           last_iteration_percentage_change, allvecs[-1],
                           allvecs[-2], np.absolute(allvecs[-2]-allvecs[-1]))
                warnings.warn(msg)

        try:
            minimisation_function = self.minimisation_dict[distribution]
        except KeyError as err:
            msg = ("Distribution requested {} is not supported in {}"
                   "Error message is {}".format(
                       distribution, self.minimisation_dict, err))
            raise KeyError(msg)

        # Ensure predictor_of_mean_flag is valid.
        check_predictor_of_mean_flag(predictor_of_mean_flag)

        if predictor_of_mean_flag.lower() in ["mean"]:
            forecast_predictor_data = forecast_predictor.data.flatten()
            truth_data = truth.data.flatten()
            forecast_var_data = forecast_var.data.flatten()
        elif predictor_of_mean_flag.lower() in ["members"]:
            truth_data = truth.data.flatten()
            forecast_predictor_data = convert_cube_data_to_2d(
                forecast_predictor)
            forecast_var_data = forecast_var.data.flatten()

        initial_guess = np.array(initial_guess, dtype=np.float32)
        forecast_predictor_data = forecast_predictor_data.astype(np.float32)
        forecast_var_data = forecast_var_data.astype(np.float32)
        truth_data = truth_data.astype(np.float32)
        sqrt_pi = np.sqrt(np.pi).astype(np.float32)

        optimised_coeffs = minimize(
            minimisation_function, initial_guess,
            args=(forecast_predictor_data, truth_data,
                  forecast_var_data, sqrt_pi, predictor_of_mean_flag),
            method="Nelder-Mead",
            options={"maxiter": self.MAX_ITERATIONS, "return_all": True})
        if not optimised_coeffs.success:
            msg = ("Minimisation did not result in convergence after "
                   "{} iterations. \n{}".format(
                       self.MAX_ITERATIONS, optimised_coeffs.message))
            warnings.warn(msg)
        calculate_percentage_change_in_last_iteration(optimised_coeffs.allvecs)
        return optimised_coeffs.x

    def normal_crps_minimiser(
            self, initial_guess, forecast_predictor, truth, forecast_var,
            sqrt_pi, predictor_of_mean_flag):
        """
        Minimisation function to calculate coefficients based on minimising the
        CRPS for a normal distribution.

        Scientific Reference:
        Gneiting, T. et al., 2005.
        Calibrated Probabilistic Forecasting Using Ensemble Model Output
        Statistics and Minimum CRPS Estimation.
        Monthly Weather Review, 133(5), pp.1098-1118.

        Parameters
        ----------
        initial_guess : List
            List of optimised coefficients.
            Order of coefficients is [c, d, a, b].
        forecast_predictor : Numpy array
            Data to be used as the predictor,
            either the ensemble mean or the ensemble members.
        truth : Numpy array
            Data to be used as truth.
        forecast_var : Numpy array
            Ensemble variance data.
        sqrt_pi : Numpy array
            Square root of Pi
        predictor_of_mean_flag : String
            String to specify the input to calculate the calibrated mean.
            Currently the ensemble mean ("mean") and the ensemble members
            ("members") are supported as the predictors.

        Returns
        -------
        result : Float
            Minimum value for the CRPS achieved.

        """
        if predictor_of_mean_flag.lower() in ["mean"]:
            beta = initial_guess[2:]
        elif predictor_of_mean_flag.lower() in ["members"]:
            beta = np.array([initial_guess[2]]+(initial_guess[3:]**2).tolist())

        new_col = np.ones(truth.shape)
        all_data = np.column_stack((new_col, forecast_predictor))
        mu = np.dot(all_data, beta)
        sigma = np.sqrt(
            initial_guess[0]**2 + initial_guess[1]**2 * forecast_var)
        xz = (truth - mu) / sigma
        normal_cdf = norm.cdf(xz)
        normal_pdf = norm.pdf(xz)
        result = np.nansum(
            sigma * (xz * (2 * normal_cdf - 1) + 2 * normal_pdf - 1 / sqrt_pi))
        if not np.isfinite(np.min(mu/sigma)):
            result = self.BAD_VALUE
        return result

    def truncated_normal_crps_minimiser(
            self, initial_guess, forecast_predictor, truth, forecast_var,
            sqrt_pi, predictor_of_mean_flag):
        """
        Minimisation function to calculate coefficients based on minimising the
        CRPS for a truncated_normal distribution.

        Scientific Reference:
        Thorarinsdottir, T.L. & Gneiting, T., 2010.
        Probabilistic forecasts of wind speed: Ensemble model
        output statistics by using heteroscedastic censored regression.
        Journal of the Royal Statistical Society.
        Series A: Statistics in Society, 173(2), pp.371-388.

        Parameters
        ----------
        initial_guess : List
            List of optimised coefficients.
            Order of coefficients is [c, d, a, b].
        forecast_predictor : Numpy array
            Data to be used as the predictor,
            either the ensemble mean or the ensemble members.
        truth : Numpy array
            Data to be used as truth.
        forecast_var : Numpy array
            Ensemble variance data.
        sqrt_pi : Numpy array
            Square root of Pi
        predictor_of_mean_flag : String
            String to specify the input to calculate the calibrated mean.
            Currently the ensemble mean ("mean") and the ensemble members
            ("members") are supported as the predictors.

        Returns
        -------
        result : Float
            Minimum value for the CRPS achieved.

        """
        if predictor_of_mean_flag.lower() in ["mean"]:
            beta = initial_guess[2:]
        elif predictor_of_mean_flag.lower() in ["members"]:
            beta = np.array([initial_guess[2]]+(initial_guess[3:]**2).tolist())

        new_col = np.ones(truth.shape)
        all_data = np.column_stack((new_col, forecast_predictor))
        mu = np.dot(all_data, beta)
        sigma = np.sqrt(
            initial_guess[0]**2 + initial_guess[1]**2 * forecast_var)
        xz = (truth - mu) / sigma
        normal_cdf = norm.cdf(xz)
        normal_pdf = norm.pdf(xz)
        x0 = mu / sigma
        normal_cdf_0 = norm.cdf(x0)
        normal_cdf_root_two = norm.cdf(np.sqrt(2) * x0)
        result = np.nansum(
            (sigma / normal_cdf_0**2) *
            (xz * normal_cdf_0 * (2 * normal_cdf + normal_cdf_0 - 2) +
             2 * normal_pdf * normal_cdf_0 -
             normal_cdf_root_two / sqrt_pi))
        if not np.isfinite(np.min(mu/sigma)) or (np.min(mu/sigma) < -3):
            result = self.BAD_VALUE
        return result


class EstimateCoefficientsForEnsembleCalibration(object):
    """
    Class focussing on estimating the optimised coefficients for ensemble
    calibration.
    """
    # Logical flag for whether initial guess estimates for the coefficients
    # will be estimated using linear regression i.e.
    # ESTIMATE_COEFFICIENTS_FROM_LINEAR_MODEL_FLAG = True, or whether default
    # values will be used instead i.e.
    # ESTIMATE_COEFFICIENTS_FROM_LINEAR_MODEL_FLAG = False.
    ESTIMATE_COEFFICIENTS_FROM_LINEAR_MODEL_FLAG = True

    def __init__(self, current_forecast, historic_forecast,
                 truth, distribution, desired_units,
                 predictor_of_mean_flag="mean"):
        """
        Create an ensemble calibration plugin that, for Nonhomogeneous Gaussian
        Regression, calculates coefficients based on historical forecasts and
        applies the coefficients to the current forecast.

        Parameters
        ----------
        current_forecast : Iris Cube or CubeList
            The cube containing the current forecast.
        historical_forecast : Iris Cube or CubeList
            The cube or cubelist containing the historical forecasts used for
            calibration.
        truth : Iris Cube or CubeList
            The cube or cubelist containing the truth used for calibration.
        distribution : String
            Name of distribution. Assume that the current forecast can be
            represented using this distribution.
        predictor_of_mean_flag : String
            String to specify the input to calculate the calibrated mean.
            Currently the ensemble mean ("mean") and the ensemble members
            ("members") are supported as the predictors.

        """
        self.current_forecast = current_forecast
        self.historic_forecast = historic_forecast
        self.truth = truth
        self.distribution = distribution
        self.desired_units = desired_units
        self.predictor_of_mean_flag = predictor_of_mean_flag
        self.minimiser = ContinuousRankedProbabilityScoreMinimisers()

        import imp
        try:
            statsmodels_found = imp.find_module('statsmodels')
            statsmodels_found = True
            import statsmodels.api as sm
            self.sm = sm
        except ImportError:
            statsmodels_found = False
            if predictor_of_mean_flag.lower() in ["members"]:
                msg = (
                    "The statsmodels can not be imported. "
                    "Will not be able to calculate an initial guess from "
                    "the individual ensemble members. "
                    "A default initial guess will be used without "
                    "estimating coefficients from a linear model.")
                warnings.warn(msg)
        self.statsmodels_found = statsmodels_found

    def __str__(self):
        result = ('<EstimateCoefficientsForEnsembleCalibration: '
                  'distribution: {};' +
                  'current_forecast: {}>' +
                  'historic_forecast: {}>' +
                  'truth')
        return result.format(
            self.distribution, self.current_forecast,
            self.historic_forecast, self.truth)

    def compute_initial_guess(
            self, truth, forecast_predictor, predictor_of_mean_flag,
            estimate_coefficients_from_linear_model_flag, no_of_members=None):
        """
        Function to compute initial guess of the a and beta components of the
        EMOS coefficients by linear regression of the forecast predictor
        and the truth, if requested. Otherwise, default values for a and b
        will be used.

        Default values have been chosen based on Figure 8 in the
        ensemble calibration documentation in
        https://exxreldocs:8099/display/TEPPV/Science+Plugin+Documents
        or
        http://www-nwp/~gevans/reports/EMOS_report_20170327.pdf

        Parameters
        ----------
        truth : Iris cube
            Cube containing the field, which will be used as truth.
        forecast_predictor : Iris cube
            Cube containing the fields to be used as the predictor,
            either the ensemble mean or the ensemble members.
        predictor_of_mean_flag : String
            String to specify the input to calculate the calibrated mean.
            Currently the ensemble mean ("mean") and the ensemble members
            ("members") are supported as the predictors.
        estimate_coefficients_from_linear_model_flag : Logical
            Flag whether coefficients should be estimated from
            the linear regression, or static estimates should be used.
        no_of_members : Int
            Number of members, if ensemble members are to be used as
            predictors. Default is None.

        Returns:
        *  initial_guess : List
            List of coefficients to be used as initial guess.
            Order of coefficients is [c, d, a, b].

        """

        if (predictor_of_mean_flag.lower() in ["mean"] and
                not estimate_coefficients_from_linear_model_flag):
            initial_guess = [1, 1, 0, 1]
        elif (predictor_of_mean_flag.lower() in ["members"] and
              not estimate_coefficients_from_linear_model_flag):
            initial_guess = [1, 1, 0] + np.repeat(1, no_of_members).tolist()
        elif estimate_coefficients_from_linear_model_flag:
            if predictor_of_mean_flag.lower() in ["mean"]:
                # Find all values that are not NaN.
                truth_not_nan = ~np.isnan(truth.data.flatten())
                forecast_not_nan = ~np.isnan(forecast_predictor.data.flatten())
                combined_not_nan = (
                    np.all(
                        np.row_stack([truth_not_nan, forecast_not_nan]),
                        axis=0))
                if not any(combined_not_nan):
                    gradient, intercept = ([np.nan, np.nan])
                else:
                    gradient, intercept, _, _, _ = (
                        stats.linregress(
                            forecast_predictor.data.flatten()[
                                combined_not_nan],
                            truth.data.flatten()[combined_not_nan]))
                initial_guess = [1, 1, intercept, gradient]
            elif predictor_of_mean_flag.lower() in ["members"]:
                if self.statsmodels_found:
                    truth_data = truth.data.flatten()
                    forecast_data = np.array(
                        convert_cube_data_to_2d(
                            forecast_predictor, transpose=False))
                    # Find all values that are not NaN.
                    truth_not_nan = ~np.isnan(truth_data)
                    forecast_not_nan = ~np.isnan(forecast_data)
                    combined_not_nan = (
                        np.all(
                            np.row_stack([truth_not_nan, forecast_not_nan]),
                            axis=0))
                    val = self.sm.add_constant(
                        forecast_data[:, combined_not_nan].T)
                    est = self.sm.OLS(truth_data[combined_not_nan], val).fit()
                    intercept = est.params[0]
                    gradient = est.params[1:]
                    initial_guess = [1, 1, intercept]+gradient.tolist()
                else:
                    initial_guess = (
                        [1, 1, 0] + np.repeat(1, no_of_members).tolist())
        return initial_guess

    def estimate_coefficients_for_ngr(self):
        """
        Using Nonhomogeneous Gaussian Regression/Ensemble Model Output
        Statistics, estimate the required coefficients from historical
        forecasts.

        The main contents of this method is:
        1. Metadata checks to ensure that the current forecast, historic
           forecast and truth exist in a form that can be processed.
        2. Loop through times within the concatenated current forecast cube.
           a. Extract the desired forecast period from the historic forecasts
              to match the current forecasts. Apply unit conversion to ensure
              that historic forecasts have the desired units for calibration.
           b. Extract the relevant truth to co-incide with the time within
              the historic forecasts. Apply unit conversion to ensure
              that the truth has the desired units for calibration.
           c. Calculate mean and variance.
           d. Calculate initial guess at coefficient values by performing a
              linear regression, if requested, otherwise default values are
              used.
           e. Perform minimisation.

        Returns:
        *  optimised_coeffs : Dictionary
            Dictionary containing a list of the optimised coefficients
            for each date.
        *  coeff_names : List
            The name of each coefficient.

        """
        def convert_to_cubelist(cubes, cube_type="forecast"):
            """
            Convert cube to cubelist, if necessary.

            Parameters
            ----------
            cubes : Iris Cube or Iris CubeList
                Cube to be converted to CubeList.
            cube_type : String
                String to describe the cube, which is being converted to a
                CubeList.

            """
            if not isinstance(cubes, iris.cube.CubeList):
                cubes = iris.cube.CubeList([cubes])
            for cube in cubes:
                if not isinstance(cube, iris.cube.Cube):
                    msg = ("The input data within the {} "
                           "is not an Iris Cube.".format(cube_type))
                    raise ValueError(msg)
            return cubes

        # Ensure predictor_of_mean_flag is valid.
        check_predictor_of_mean_flag(self.predictor_of_mean_flag)

        # Setting default values for optimised_coeffs and coeff_names.
        optimised_coeffs = {}
        coeff_names = ["gamma", "delta", "a", "beta"]

        # Set default values for whether there are NaN values within the
        # initial guess.
        nan_in_initial_guess = False

        for var in [self.current_forecast, self.historic_forecast,
                    self.truth]:
            if (isinstance(var, iris.cube.Cube) or
                    isinstance(var, iris.cube.CubeList)):
                current_forecast_cubes = self.current_forecast
                historic_forecast_cubes = self.historic_forecast
                truth_cubes = self.truth
            else:
                msg = ("{} is not a Cube or CubeList."
                       "Returning default values for optimised_coeffs {} "
                       "and coeff_names {}.").format(
                           var, optimised_coeffs, coeff_names)
                warnings.warn(msg)
                return optimised_coeffs, coeff_names

        current_forecast_cubes = (
            convert_to_cubelist(
                current_forecast_cubes, cube_type="current forecast"))
        historic_forecast_cubes = (
            convert_to_cubelist(
                historic_forecast_cubes, cube_type="historic forecast"))
        truth_cubes = convert_to_cubelist(truth_cubes, cube_type="truth")

        if (len(current_forecast_cubes) == 0 or
                len(historic_forecast_cubes) == 0 or len(truth_cubes) == 0):
            msg = ("Insufficient input data present to estimate "
                   "coefficients using NGR. "
                   "\nNumber of current_forecast_cubes: {}"
                   "\nNumber of historic_forecast_cubes: {}"
                   "\nNumber of truth_cubes: {}".format(
                       len(current_forecast_cubes),
                       len(historic_forecast_cubes), len(truth_cubes)))
            warnings.warn(msg)
            return optimised_coeffs, coeff_names

        rename_coordinate(
            current_forecast_cubes, "ensemble_member_id", "realization")
        rename_coordinate(
            historic_forecast_cubes, "ensemble_member_id", "realization")

        current_forecast_cubes = concatenate_cubes(
            current_forecast_cubes)
        historic_forecast_cubes = concatenate_cubes(
            historic_forecast_cubes)
        truth_cubes = concatenate_cubes(truth_cubes)

        for current_forecast_cube in current_forecast_cubes.slices_over(
                "time"):
            date = unit.num2date(
                current_forecast_cube.coord("time").points,
                current_forecast_cube.coord("time").units.name,
                current_forecast_cube.coord("time").units.calendar)[0]
            # Extract desired forecast_period from historic_forecast_cubes.
            forecast_period_constr = iris.Constraint(
                forecast_period=current_forecast_cube.coord(
                    "forecast_period").points)
            historic_forecast_cube = historic_forecast_cubes.extract(
                forecast_period_constr)

            # Extract truth matching the time of the historic forecast.
            truth_constr = iris.Constraint(
                forecast_reference_time=historic_forecast_cube.coord(
                    "time").points)
            truth_cube = truth_cubes.extract(truth_constr)

            if truth_cube is None:
                msg = ("Unable to calibrate for the time points {} "
                       "as no truth data is available."
                       "Moving on to try to calibrate "
                       "next time point.".format(
                           historic_forecast_cube.coord("time").points))
                warnings.warn(msg)
                continue

            # Make sure inputs have the same units.
            historic_forecast_cube.convert_units(self.desired_units)
            truth_cube.convert_units(self.desired_units)

            if self.predictor_of_mean_flag.lower() in ["mean"]:
                no_of_members = None
                forecast_predictor = historic_forecast_cube.collapsed(
                    "realization", iris.analysis.MEAN)
            elif self.predictor_of_mean_flag.lower() in ["members"]:
                no_of_members = len(
                    historic_forecast_cube.coord("realization").points)
                forecast_predictor = historic_forecast_cube

            forecast_var = historic_forecast_cube.collapsed(
                "realization", iris.analysis.VARIANCE)

            # Computing initial guess for EMOS coefficients
            # If no initial guess from a previous iteration, or if there
            # are NaNs in the initial guess, calculate an initial guess.
            if "initial_guess" not in locals() or nan_in_initial_guess:
                initial_guess = self.compute_initial_guess(
                    truth_cube, forecast_predictor,
                    self.predictor_of_mean_flag,
                    self.ESTIMATE_COEFFICIENTS_FROM_LINEAR_MODEL_FLAG,
                    no_of_members=no_of_members)

            if np.any(np.isnan(initial_guess)):
                nan_in_initial_guess = True

            if not nan_in_initial_guess:
                # Need to access the x attribute returned by the
                # minimisation function.
                optimised_coeffs[date] = (
                    self.minimiser.crps_minimiser_wrapper(
                        initial_guess, forecast_predictor,
                        truth_cube, forecast_var,
                        self.predictor_of_mean_flag,
                        self.distribution.lower()))
                initial_guess = optimised_coeffs[date]
            else:
                optimised_coeffs[date] = initial_guess

        return optimised_coeffs, coeff_names


class ApplyCoefficientsFromEnsembleCalibration(object):
    """
    Class to apply the optimised EMOS coefficients to future dates.

    """
    def __init__(
            self, current_forecast, optimised_coeffs, coeff_names,
            predictor_of_mean_flag="mean"):
        """
        Create an ensemble calibration plugin that, for Nonhomogeneous Gaussian
        Regression, applies coefficients created using on historical forecasts
        and applies the coefficients to the current forecast.

        Parameters
        ----------
        current_forecast : Iris Cube or CubeList
            The Cube or CubeList containing the current forecast.
        optimised_coeffs : Dictionary
            Dictionary containing a list of the optimised coefficients
            for each date.
        coeff_names : List
            The name of each coefficient.
        predictor_of_mean_flag : String
            String to specify the input to calculate the calibrated mean.
            Currently the ensemble mean ("mean") and the ensemble members
            ("members") are supported as the predictors.

        """
        self.current_forecast = current_forecast
        self.optimised_coeffs = optimised_coeffs
        self.coeff_names = coeff_names
        self.predictor_of_mean_flag = predictor_of_mean_flag

    def _find_coords_of_length_one(self, cube, add_dimension=True):
        """
        Function to find all coordinates with a length of 1.

        Parameters
        ----------
        cube : Iris cube
            Cube
        add_dimension : Logical
            Adds a dimension of 0 to each coordinate. A tuple is appended.

        Returns:
        *  length_one_coords : List or List of tuples
            List of length one coordinates or list of tuples containing
            length one coordinates and the dimension.

        """
        length_one_coords = []
        for coord in cube.coords():
            if len(coord.points) == 1:  # Find length one coordinates
                if add_dimension:
                    length_one_coords.append((coord, 0))
                else:
                    length_one_coords.append(coord)
        return length_one_coords

    def _separate_length_one_coords_into_aux_and_dim(
            self, length_one_coords, dim_coords=["time"]):
        """
        Function to separate coordinates into auxiliary and dimension
        coordinates.

        Parameters
        ----------
        length_one_coords : Iterable of coordinates
            The coordinates to be checked for length one coordinates.
        dim_coords : List of coordinates
            The length one coordinates to be made dimension coordinates.

        Returns:
        *  length_one_coords_for_aux_coords
            List of length one coordinates to be auxiliary coordinates, i.e.
            not in the dim_coords list.
        *  length_one_coords_for_dim_coords
            List of length one coordinates to be dimension coordinates,
            according to dim_coords list.

        """
        length_one_coords_for_aux_coords = []
        length_one_coords_for_dim_coords = []
        for coord in length_one_coords:
            if coord[0].name() in dim_coords:
                length_one_coords_for_dim_coords.append(coord)
            else:
                length_one_coords_for_aux_coords.append(coord)
        return (
            length_one_coords_for_aux_coords,
            length_one_coords_for_dim_coords)

    def _create_coefficient_cube(
            self, cube, optimised_coeffs_at_date, coeff_names):
        """
        Function to create a cube to store the coefficients used in the
        ensemble calibration.

        Parameters
        ----------
        cube : Iterable of coordinates
            The coordinates to be checked for length one coordinates.
        optimised_coeffs_at_date : List of coefficients
            Optimised coefficients for a particular date.
        coeff_names : List
            List of coefficient names.


        Returns:
        *  coeff_cubes : Iris cube
            Cube containing the coefficient value as the data array.

        """
        length_one_coords = self._find_coords_of_length_one(cube)

        length_one_coords_for_aux_coords, length_one_coords_for_dim_coords = (
            self._separate_length_one_coords_into_aux_and_dim(
                length_one_coords))

        coeff_cubes = iris.cube.CubeList([])
        for coeff, coeff_name in zip(optimised_coeffs_at_date, coeff_names):
            cube = iris.cube.Cube(
                [coeff], long_name=coeff_name, attributes=cube.attributes,
                aux_coords_and_dims=length_one_coords_for_aux_coords,
                dim_coords_and_dims=length_one_coords_for_dim_coords)
            coeff_cubes.append(cube)
        return coeff_cubes

    def apply_params_entry(self):
        """
        Wrapping function to calculate the forecast predictor and forecast
        variance prior to applying coefficients to the current forecast.

        Returns
        -------
        calibrated_forecast_predictor : CubeList
            CubeList containing both the calibrated version of the ensemble
            predictor, either the ensemble mean/members.
        calibrated_forecast_variance : CubeList
            CubeList containing both the calibrated version of the ensemble
            variance, either the ensemble mean/members.
        calibrated_forecast_coefficients : CubeList
            CubeList containing both the coefficients for calibrating
            the ensemble.

        """
        # Ensure predictor_of_mean_flag is valid.
        check_predictor_of_mean_flag(self.predictor_of_mean_flag)

        rename_coordinate(
            self.current_forecast, "ensemble_member_id", "realization")

        current_forecast_cubes = concatenate_cubes(
            self.current_forecast)

        if self.predictor_of_mean_flag.lower() in ["mean"]:
            forecast_predictors = current_forecast_cubes.collapsed(
                "realization", iris.analysis.MEAN)
        elif self.predictor_of_mean_flag.lower() in ["members"]:
            forecast_predictors = current_forecast_cubes

        forecast_vars = current_forecast_cubes.collapsed(
            "realization", iris.analysis.VARIANCE)

        (calibrated_forecast_predictor, calibrated_forecast_var,
         calibrated_forecast_coefficients) = self._apply_params(
             forecast_predictors, forecast_vars, self.optimised_coeffs,
             self.coeff_names, self.predictor_of_mean_flag)
        return (calibrated_forecast_predictor,
                calibrated_forecast_var,
                calibrated_forecast_coefficients)

    def _apply_params(
            self, forecast_predictors, forecast_vars, optimised_coeffs,
            coeff_names, predictor_of_mean_flag):
        """
        Function to apply EMOS coefficients to all required dates.

        Parameters
        ----------
        forecast_predictors : Iris cube
            Cube containing the forecast predictor e.g. ensemble mean
            or ensemble members.
        forecast_vars : Iris cube.
            Cube containing the forecast variance e.g. ensemble variance.
        optimised_coeffs : List
            Coefficients for all dates.
        coeff_names : List
            Coefficient names.
        predictor_of_mean_flag : String
            String to specify the input to calculate the calibrated mean.
            Currently the ensemble mean ("mean") and the ensemble members
            ("members") are supported as the predictors.

        Returns:
        calibrated_forecast_predictor_all_dates : CubeList
            List of cubes containing the calibrated forecast predictor.
        calibrated_forecast_var_all_dates : CubeList
            List of cubes containing the calibrated forecast variance.
        calibrated_forecast_coefficients_all_dates : CubeList
            List of cubes containing the coefficients used for calibration.

        """
        calibrated_forecast_predictor_all_dates = iris.cube.CubeList()
        calibrated_forecast_var_all_dates = iris.cube.CubeList()
        calibrated_forecast_coefficients_all_dates = iris.cube.CubeList()

        for forecast_predictor, forecast_var in zip(
                forecast_predictors.slices_over("time"),
                forecast_vars.slices_over("time")):

            date = unit.num2date(
                forecast_predictor.coord("time").points,
                forecast_predictor.coord("time").units.name,
                forecast_predictor.coord("time").units.calendar)[0]

            with iris.FUTURE.context(cell_datetime_objects=True):
                constr = iris.Constraint(time=date)
                forecast_predictor_at_date = forecast_predictor.extract(constr)
                forecast_var_at_date = forecast_var.extract(constr)

            # If the coefficients are not available for the date, use the
            # raw ensemble forecast as the calibrated ensemble forecast.
            if date not in optimised_coeffs.keys():
                msg = ("Ensemble calibration not available "
                       "for forecasts with start time of {}. "
                       "Coefficients not available".format(
                           date.strftime("%Y%m%d%H%M")))
                warnings.warn(msg)
                calibrated_forecast_predictor_at_date = (
                    forecast_predictor_at_date.copy())
                calibrated_forecast_var_at_date = forecast_var_at_date.copy()
                optimised_coeffs[date] = np.full(len(coeff_names), np.nan)
                coeff_cubes = self._create_coefficient_cube(
                    forecast_predictor_at_date, optimised_coeffs, coeff_names)
            else:
                optimised_coeffs_at_date = (
                    optimised_coeffs[date])

                # Assigning coefficients to coefficient names.
                if len(optimised_coeffs_at_date) == len(coeff_names):
                    optimised_coeffs_at_date = dict(
                        zip(coeff_names, optimised_coeffs_at_date))
                elif len(optimised_coeffs_at_date) > len(coeff_names):
                    excess_beta = (
                        optimised_coeffs_at_date[len(coeff_names):].tolist())
                    optimised_coeffs_at_date = (
                        dict(zip(coeff_names, optimised_coeffs_at_date)))
                    optimised_coeffs_at_date["beta"] = np.array(
                        [optimised_coeffs_at_date["beta"]]+excess_beta)
                else:
                    msg = ("Number of coefficient names {} with names {} "
                           "is not equal to the number of "
                           "optimised_coeffs_at_date values {} "
                           "with values {} or the number of "
                           "coefficients is not greater than the "
                           "number of coefficient names. Can not continue "
                           "if the number of coefficient names out number "
                           "the number of coefficients".format(
                               len(coeff_names), coeff_names,
                               len(optimised_coeffs_at_date),
                               optimised_coeffs_at_date))
                    raise ValueError(msg)

                if predictor_of_mean_flag.lower() in ["mean"]:
                    # Calculate predicted mean = a + b*X, where X is the
                    # raw ensemble mean. In this case, b = beta.
                    beta = [optimised_coeffs_at_date["a"],
                            optimised_coeffs_at_date["beta"]]
                    forecast_predictor_flat = (
                        forecast_predictor_at_date.data.flatten())
                    new_col = np.ones(forecast_predictor_flat.shape)
                    all_data = np.column_stack(
                        (new_col, forecast_predictor_flat))
                    predicted_mean = np.dot(all_data, beta)
                    calibrated_forecast_predictor_at_date = (
                        forecast_predictor_at_date)
                elif predictor_of_mean_flag.lower() in ["members"]:
                    # Calculate predicted mean = a + b*X, where X is the
                    # raw ensemble mean. In this case, b = beta^2.
                    beta = np.concatenate(
                        [[optimised_coeffs_at_date["a"]],
                         optimised_coeffs_at_date["beta"]**2])
                    forecast_predictor_flat = (
                        convert_cube_data_to_2d(
                            forecast_predictor_at_date))
                    forecast_var_flat = forecast_var_at_date.data.flatten()

                    new_col = np.ones(forecast_var_flat.shape)
                    all_data = (
                        np.column_stack((new_col, forecast_predictor_flat)))
                    predicted_mean = np.dot(all_data, beta)
                    # Calculate mean of ensemble members, as only the
                    # calibrated ensemble mean will be returned.
                    calibrated_forecast_predictor_at_date = (
                        forecast_predictor_at_date.collapsed(
                            "realization", iris.analysis.MEAN))

                xlen = len(forecast_predictor_at_date.coord(axis="x").points)
                ylen = len(forecast_predictor_at_date.coord(axis="y").points)
                predicted_mean = np.reshape(predicted_mean, (ylen, xlen))
                calibrated_forecast_predictor_at_date.data = predicted_mean

                # Calculating the predicted variance, based on the
                # raw variance S^2, where predicted variance = c + dS^2,
                # where c = (gamma)^2 and d = (delta)^2
                predicted_var = (optimised_coeffs_at_date["gamma"]**2 +
                                 optimised_coeffs_at_date["delta"]**2 *
                                 forecast_var_at_date.data)

                calibrated_forecast_var_at_date = forecast_var_at_date
                calibrated_forecast_var_at_date.data = predicted_var

                coeff_cubes = self._create_coefficient_cube(
                    calibrated_forecast_predictor_at_date,
                    optimised_coeffs[date], coeff_names)

            calibrated_forecast_predictor_all_dates.append(
                calibrated_forecast_predictor_at_date)
            calibrated_forecast_var_all_dates.append(
                calibrated_forecast_var_at_date)
            calibrated_forecast_coefficients_all_dates.extend(coeff_cubes)

        return (calibrated_forecast_predictor_all_dates,
                calibrated_forecast_var_all_dates,
                calibrated_forecast_coefficients_all_dates)


class EnsembleCalibration(object):
    """
    Plugin to wrap the core EMOS processes:
    1. Estimate optimised EMOS coefficients from training period.
    2. Apply optimised EMOS coefficients for future dates.

    """
    def __init__(self, current_forecast,
                 historic_forecast, truth,
                 calibration_method, distribution, desired_units,
                 predictor_of_mean_flag="mean"):
        """
        Create an ensemble calibration plugin that, for Nonhomogeneous Gaussian
        Regression, calculates coefficients based on historical forecasts and
        applies the coefficients to the current forecast.

        Parameters
        ----------
        current_forecast : Iris Cube or CubeList
            The Cube or CubeList that provides the input forecast for
            the current cycle.
        historic_forecast : Iris Cube or CubeList
            The Cube or CubeList that provides the input historic forecasts for
            calibration.
        truth : Iris Cube or CubeList
            The Cube or CubeList that provides the input truth for calibration
            with dates matching the historic forecasts.
        calibration_method : String
            The calibration method that will be applied.
            Supported methods are:
                ensemble model output statistics
                nonhomogeneous gaussian regression
            Currently these methods are not supported:
                logistic regression
                bayesian model averaging
        distribution : String
            The distribution that will be used for calibration. This will be
            dependent upon the input phenomenon. This has to be supported by
            the minimisation functions in
            ContinuousRankedProbabilityScoreMinimisers.
        predictor_of_mean_flag : String
            String to specify the input to calculate the calibrated mean.
            Currently the ensemble mean ("mean") and the ensemble members
            ("members") are supported as the predictors.

        """
        self.current_forecast = current_forecast
        self.historic_forecast = historic_forecast
        self.truth = truth
        self.calibration_method = calibration_method
        self.distribution = distribution
        self.desired_units = desired_units
        self.predictor_of_mean_flag = predictor_of_mean_flag

    def __str__(self):
        result = ('<EnsembleCalibration: ' +
                  'calibration_method: {}' +
                  'distribution: {};' +
                  'desired_units: {};' +
                  'predictor_of_mean_flag: {};' +
                  'current_forecast: {}>' +
                  'historic_forecast: {}>' +
                  'truth: {}>')
        return result.format(
            self.calibration_method, self.distribution, self.desired_units,
            self.predictor_of_mean_flag, self.current_forecast,
            self.historic_forecast, self.truth)

    def process(self):
        """
        Performs ensemble calibration through the following steps:
        1. Estimate optimised coefficients from training period.
        2. Apply optimised coefficients to current forecast.

        Returns:
        *  calibrated_forecast_predictor_and_variance : CubeList
            CubeList containing the calibrated forecast predictor and
            calibrated forecast variance.

        """
        def format_calibration_method(calibration_method):
            """Lowercase input string, and replace underscores with spaces."""
            return calibration_method.lower().replace("_", " ")

        # Ensure predictor_of_mean_flag is valid.
        check_predictor_of_mean_flag(self.predictor_of_mean_flag)

        if (format_calibration_method(self.calibration_method) in
            ["ensemble model output statistics",
             "nonhomogeneous gaussian regression"]):
            if (format_calibration_method(self.distribution) in
                    ["gaussian", "truncated gaussian"]):
                ec = EstimateCoefficientsForEnsembleCalibration(
                    self.current_forecast,
                    self.historic_forecast,
                    self.truth, self.distribution,
                    self.desired_units,
                    predictor_of_mean_flag=self.predictor_of_mean_flag)
                optimised_coeffs, coeff_names = (
                    ec.estimate_coefficients_for_ngr())
        else:
            msg = ("Other calibration methods are not available. "
                   "{} is not available".format(
                       format_calibration_method(self.calibration_method)))
            raise ValueError(msg)
        ac = ApplyCoefficientsFromEnsembleCalibration(
            self.current_forecast, optimised_coeffs, coeff_names,
            predictor_of_mean_flag=self.predictor_of_mean_flag)
        (calibrated_forecast_predictor, calibrated_forecast_variance,
         calibrated_forecast_coefficients) = ac.apply_params_entry()
        calibrated_forecast_predictor_and_variance = iris.cube.CubeList([
            calibrated_forecast_predictor, calibrated_forecast_variance])
        return calibrated_forecast_predictor_and_variance


class GeneratePercentilesFromMeanAndVariance(object):
    """
    Plugin focussing on generating percentiles from mean and variance.
    In combination with the EnsembleReordering plugin, this is Ensemble
    Copula Coupling.
    """

    def __init__(self, calibrated_forecast_predictor_and_variance,
                 raw_forecast):
        """
        Parameters
        ----------
        calibrated_forecast_predictor_and_variance : Iris CubeList
            CubeList containing the calibrated forecast predictor and
            calibrated forecast variance.
        raw_forecast : Iris Cube or CubeList
            Cube or CubeList that is expected to be the raw
            (uncalibrated) forecast.

        """
        (self.calibrated_forecast_predictor,
         self.calibrated_forecast_variance) = (
             calibrated_forecast_predictor_and_variance)
        self.raw_forecast = raw_forecast

    def _create_cube_with_percentiles(
            self, percentiles, template_cube, cube_data):
        """
        Create a cube with a percentile coordinate based on a template cube.

        Parameters
        ----------
        percentiles : List
            Ensemble percentiles.
        template_cube : Iris cube
            Cube to copy majority of coordinate definitions from.
        cube_data : Numpy array
            Data to insert into the template cube.
            The data is expected to have the shape of
            percentiles (0th dimension), time (1st dimension),
            y_coord (2nd dimension), x_coord (3rd dimension).

        Returns
        -------
        String
            Coordinate name of the matched coordinate.

        """
        percentile_coord = iris.coords.DimCoord(
            np.float32(percentiles), long_name="percentile",
            units=unit.Unit("1"), var_name="percentile")

        time_coord = template_cube.coord("time")
        y_coord = template_cube.coord(axis="y")
        x_coord = template_cube.coord(axis="x")

        dim_coords_and_dims = [
            (percentile_coord, 0), (time_coord, 1),
            (y_coord, 2), (x_coord, 3)]

        frt_coord = template_cube.coord("forecast_reference_time")
        fp_coord = template_cube.coord("forecast_period")
        aux_coords_and_dims = [(frt_coord, 1), (fp_coord, 1)]

        metadata_dict = copy.deepcopy(template_cube.metadata._asdict())

        cube = iris.cube.Cube(
            cube_data, dim_coords_and_dims=dim_coords_and_dims,
            aux_coords_and_dims=aux_coords_and_dims, **metadata_dict)
        cube.attributes = template_cube.attributes
        cube.cell_methods = template_cube.cell_methods
        return cube

    def _mean_and_variance_to_percentiles(
            self, calibrated_forecast_predictor, calibrated_forecast_variance,
            percentiles):
        """
        Function returning percentiles based on the supplied
        mean and variance. The percentiles are created by assuming a
        Gaussian distribution and calculating the value of the phenomenon at
        specific points within the distribution.

        Parameters
        ----------
        calibrated_forecast_predictor : cube
            Predictor for the calibrated forecast i.e. the mean.
        calibrated_forecast_variance : cube
            Variance for the calibrated forecast.
        percentiles : List
            Percentiles at which to calculate the value of the phenomenon at.

        Returns
        -------
        percentile_cube : Iris cube
            Cube containing the values for the phenomenon at each of the
            percentiles requested.

        """
        if not calibrated_forecast_predictor.coord_dims("time"):
            calibrated_forecast_predictor = iris.util.new_axis(
                calibrated_forecast_predictor, "time")
        if not calibrated_forecast_variance.coord_dims("time"):
            calibrated_forecast_variance = iris.util.new_axis(
                calibrated_forecast_variance, "time")

        calibrated_forecast_predictor_data = (
            calibrated_forecast_predictor.data.flatten())
        calibrated_forecast_variance_data = (
            calibrated_forecast_variance.data.flatten())

        result = np.zeros((calibrated_forecast_predictor_data.shape[0],
                           len(percentiles)))

        # Loop over percentiles, and use a normal distribution with the mean
        # and variance to calculate the values at each percentile.
        for index, percentile in enumerate(percentiles):
            percentile_list = np.repeat(
                percentile, len(calibrated_forecast_predictor_data))
            result[:, index] = norm.ppf(
                percentile_list, loc=calibrated_forecast_predictor_data,
                scale=np.sqrt(calibrated_forecast_variance_data))
            # If percent point function (PPF) returns NaNs, fill in
            # mean instead of NaN values. NaN will only be generated if the
            # variance is zero. Therefore, if the variance is zero, the mean
            # value is used for all gridpoints with a NaN.
            if np.any(calibrated_forecast_variance_data == 0):
                nan_index = np.argwhere(np.isnan(result[:, index]))
                result[nan_index, index] = (
                    calibrated_forecast_predictor_data[nan_index])
            if np.any(np.isnan(result)):
                msg = ("NaNs are present within the result for the {} "
                       "percentile. Unable to calculate the percent point "
                       "function.")
                raise ValueError(msg)

        result = result.T

        t_coord = calibrated_forecast_predictor.coord("time")
        y_coord = calibrated_forecast_predictor.coord(axis="y")
        x_coord = calibrated_forecast_predictor.coord(axis="x")

        result = result.reshape(
            len(percentiles), len(t_coord.points), len(y_coord.points),
            len(x_coord.points))
        percentile_cube = self._create_cube_with_percentiles(
            percentiles, calibrated_forecast_predictor, result)

        percentile_cube.cell_methods = {}
        return percentile_cube

    def _create_percentiles(
            self, no_of_percentiles, sampling="quantile"):
        """
        Function to create percentiles.

        Parameters
        ----------
        no_of_percentiles : Int
            Number of percentiles.
        sampling : String
            Type of sampling of the distribution to produce a set of
            percentiles e.g. quantile or random.
            Accepted options for sampling are:
            Quantile: A regular set of equally-spaced percentiles aimed
                      at dividing a Cumulative Distribution Function into
                      blocks of equal probability.
            Random: A random set of ordered percentiles.

        For further details, Flowerdew, J., 2014.
        Calibrating ensemble reliability whilst preserving spatial structure.
        Tellus, Series A: Dynamic Meteorology and Oceanography, 66(1), pp.1-20.
        Schefzik, R., Thorarinsdottir, T.L. & Gneiting, T., 2013.
        Uncertainty Quantification in Complex Simulation Models Using Ensemble
        Copula Coupling.
        Statistical Science, 28(4), pp.616-640.

        Returns
        -------
        percentiles : List
            Percentiles calculated using the sampling technique specified.

        """
        if sampling in ["quantile"]:
            percentiles = np.linspace(
                1/float(1+no_of_percentiles),
                no_of_percentiles/float(1+no_of_percentiles),
                no_of_percentiles).tolist()
        elif sampling in ["random"]:
            percentiles = []
            for _ in range(no_of_percentiles):
                percentiles.append(
                    random.uniform(
                        1/float(1+no_of_percentiles),
                        no_of_percentiles/float(1+no_of_percentiles)))
            percentiles = sorted(percentiles)
        else:
            msg = "The {} sampling option is not yet implemented.".format(
                sampling)
            raise ValueError(msg)
        return percentiles

    def process(self):
        """
        Generate ensemble percentiles from the mean and variance.

        Returns
        -------
        calibrated_forecast_percentiles : Iris cube
            Cube for calibrated percentiles.

        """
        raw_forecast = self.raw_forecast

        calibrated_forecast_predictor = concatenate_cubes(
            self.calibrated_forecast_predictor)
        calibrated_forecast_variance = concatenate_cubes(
            self.calibrated_forecast_variance)
        rename_coordinate(
            self.raw_forecast, "ensemble_member_id", "realization")
        raw_forecast_members = concatenate_cubes(self.raw_forecast)

        no_of_percentiles = len(
            raw_forecast_members.coord("realization").points)

        percentiles = self._create_percentiles(no_of_percentiles)
        calibrated_forecast_percentiles = (
            self._mean_and_variance_to_percentiles(
                calibrated_forecast_predictor,
                calibrated_forecast_variance,
                percentiles))

        return calibrated_forecast_percentiles


class EnsembleReordering(object):
    """
    Plugin for applying the reordering step of Ensemble Copula Coupling,
    in order to generate ensemble members from percentiles.
    The percentiles are assumed to be in ascending order.

    Reference:
    Schefzik, R., Thorarinsdottir, T.L. & Gneiting, T., 2013.
    Uncertainty Quantification in Complex Simulation Models Using Ensemble
    Copula Coupling.
    Statistical Science, 28(4), pp.616-640.

    """
    def __init__(self, calibrated_forecast, raw_forecast):
        """
        Parameters
        ----------
        calibrated_forecast : Iris Cube or CubeList
            The cube or cubelist containing the calibrated forecast members.
        raw_forecast : Iris Cube or CubeList
            The cube or cubelist containing the raw (uncalibrated) forecast.

        """
        self.calibrated_forecast = calibrated_forecast
        self.raw_forecast = raw_forecast

    def rank_ecc(self, calibrated_forecast_percentiles, raw_forecast_members):
        """
        Function to apply Ensemble Copula Coupling. This ranks the calibrated
        forecast members based on a ranking determined from the raw forecast
        members.

        Parameters
        ----------
        calibrated_forecast_percentiles : cube
            Cube for calibrated percentiles. The percentiles are assumed to be
            in ascending order.
        raw_forecast_members : cube
            Cube containing the raw (uncalibrated) forecasts.

        Returns
        -------
        Iris cube
            Cube for calibrated members where at a particular grid point,
            the ranking of the values within the ensemble matches the ranking
            from the raw ensemble.

        """
        results = iris.cube.CubeList([])
        for rawfc, calfc in zip(
                raw_forecast_members.slices_over("time"),
                calibrated_forecast_percentiles.slices_over("time")):
            random_data = np.random.random(rawfc.data.shape)
            # Lexsort returns the indices sorted firstly by the primary key,
            # the raw forecast data, and secondly by the secondary key, an
            # array of random data, in order to split tied values randomly.
            sorting_index = np.lexsort((random_data, rawfc.data), axis=0)
            # Returns the indices that would sort the array.
            ranking = np.argsort(sorting_index, axis=0)
            # Index the calibrated forecast data using the ranking array.
            # np.choose allows indexing of a 3d array using a 3d array,
            calfc.data = np.choose(ranking, calfc.data)
            results.append(calfc)
        return concatenate_cubes(results)

    def process(self):
        """
        Returns
        -------
        calibrated_forecast_members : cube
            Cube for a new ensemble member where all points within the dataset
            are representative of a specified probability threshold across the
            whole domain.
        """
        rename_coordinate(
            self.raw_forecast, "ensemble_member_id", "realization")
        calibrated_forecast_percentiles = concatenate_cubes(
            self.calibrated_forecast,
            coords_to_slice_over=["percentile", "time"])
        raw_forecast_members = concatenate_cubes(self.raw_forecast)
        calibrated_forecast_members = self.rank_ecc(
            calibrated_forecast_percentiles, raw_forecast_members)
        rename_coordinate(
            calibrated_forecast_members, "percentile", "realization")
        return calibrated_forecast_members
