# Copyright (c) 2012, 2013 GPy authors (see AUTHORS.txt).
# Licensed under the BSD 3-clause license (see LICENSE.txt)
import GPy
import pytest
from GPy.core.parameterization.param import Param
import numpy as np
from ..util.config import config


verbose = 0

try:
    from ..kern.src import coregionalize_cython

    cython_coregionalize_working = config.getboolean("cython", "working")
except ImportError:
    cython_coregionalize_working = False


class Kern_check_model(GPy.core.Model):
    """
    This is a dummy model class used as a base class for checking that the
    gradients of a given kernel are implemented correctly. It enables
    checkgrad() to be called independently on a kernel.
    """

    def __init__(self, kernel=None, dL_dK=None, X=None, X2=None):
        super(Kern_check_model, self).__init__("kernel_test_model")
        if kernel == None:
            kernel = GPy.kern.RBF(1)
        kernel.randomize(loc=1, scale=0.1)
        if X is None:
            X = np.random.randn(20, kernel.input_dim)
        if dL_dK is None:
            if X2 is None:
                dL_dK = np.random.rand(X.shape[0], X.shape[0])
            else:
                dL_dK = np.random.rand(X.shape[0], X2.shape[0])

        self.kernel = kernel
        self.X = X
        self.X2 = X2
        self.dL_dK = dL_dK

    def is_positive_semi_definite(self):
        v = np.linalg.eig(self.kernel.K(self.X))[0]
        if any(v.real <= -1e-10):
            print(v.real.min())
            return False
        else:
            return True

    def log_likelihood(self):
        return np.sum(self.dL_dK * self.kernel.K(self.X, self.X2))


class Kern_check_dK_dtheta(Kern_check_model):
    """
    This class allows gradient checks for the gradient of a kernel with
    respect to parameters.
    """

    def __init__(self, kernel=None, dL_dK=None, X=None, X2=None):
        super(Kern_check_dK_dtheta, self).__init__(
            kernel=kernel, dL_dK=dL_dK, X=X, X2=X2
        )
        self.link_parameter(self.kernel)

    def parameters_changed(self):
        return self.kernel.update_gradients_full(self.dL_dK, self.X, self.X2)


class Kern_check_dKdiag_dtheta(Kern_check_model):
    """
    This class allows gradient checks of the gradient of the diagonal of a
    kernel with respect to the parameters.
    """

    def __init__(self, kernel=None, dL_dK=None, X=None):
        super(Kern_check_dKdiag_dtheta, self).__init__(
            kernel=kernel, dL_dK=dL_dK, X=X, X2=None
        )
        self.link_parameter(self.kernel)

    def log_likelihood(self):
        return (np.diag(self.dL_dK) * self.kernel.Kdiag(self.X)).sum()

    def parameters_changed(self):
        self.kernel.update_gradients_diag(np.diag(self.dL_dK), self.X)


class Kern_check_dK_dX(Kern_check_model):
    """This class allows gradient checks for the gradient of a kernel with respect to X."""

    def __init__(self, kernel=None, dL_dK=None, X=None, X2=None):
        super(Kern_check_dK_dX, self).__init__(kernel=kernel, dL_dK=dL_dK, X=X, X2=X2)
        self.X = Param("X", X)
        self.link_parameter(self.X)

    def parameters_changed(self):
        self.X.gradient[:] = self.kernel.gradients_X(self.dL_dK, self.X, self.X2)


class Kern_check_dKdiag_dX(Kern_check_dK_dX):
    """This class allows gradient checks for the gradient of a kernel diagonal with respect to X."""

    def __init__(self, kernel=None, dL_dK=None, X=None, X2=None):
        super(Kern_check_dKdiag_dX, self).__init__(
            kernel=kernel, dL_dK=dL_dK, X=X, X2=None
        )

    def log_likelihood(self):
        return (np.diag(self.dL_dK) * self.kernel.Kdiag(self.X)).sum()

    def parameters_changed(self):
        self.X.gradient[:] = self.kernel.gradients_X_diag(self.dL_dK.diagonal(), self.X)


class Kern_check_d2K_dXdX(Kern_check_model):
    """This class allows gradient checks for the secondderivative of a kernel with respect to X."""

    def __init__(self, kernel=None, dL_dK=None, X=None, X2=None):
        super(Kern_check_d2K_dXdX, self).__init__(
            kernel=kernel, dL_dK=dL_dK, X=X, X2=X2
        )
        self.X = Param("X", X.copy())
        self.link_parameter(self.X)
        self.Xc = X.copy()

    def log_likelihood(self):
        if self.X2 is None:
            return self.kernel.gradients_X(self.dL_dK, self.X, self.Xc).sum()
        return self.kernel.gradients_X(self.dL_dK, self.X, self.X2).sum()

    def parameters_changed(self):
        # if self.kernel.name == 'rbf':
        #    import ipdb;ipdb.set_trace()
        if self.X2 is None:
            grads = -self.kernel.gradients_XX(self.dL_dK, self.X).sum(1).sum(1)
        else:
            grads = (
                -self.kernel.gradients_XX(self.dL_dK.T, self.X2, self.X).sum(0).sum(1)
            )
        self.X.gradient[:] = grads


class Kern_check_d2Kdiag_dXdX(Kern_check_model):
    """This class allows gradient checks for the second derivative of a kernel with respect to X."""

    def __init__(self, kernel=None, dL_dK=None, X=None):
        super(Kern_check_d2Kdiag_dXdX, self).__init__(kernel=kernel, dL_dK=dL_dK, X=X)
        self.X = Param("X", X)
        self.link_parameter(self.X)
        self.Xc = X.copy()

    def log_likelihood(self):
        l = 0.0
        for i in range(self.X.shape[0]):
            l += self.kernel.gradients_X(
                self.dL_dK[[i], [i]], self.X[[i]], self.Xc[[i]]
            ).sum()
        return l

    def parameters_changed(self):
        grads = -self.kernel.gradients_XX_diag(self.dL_dK.diagonal(), self.X)
        self.X.gradient[:] = grads.sum(-1)


def check_kernel_gradient_functions(
    kern, X=None, X2=None, output_ind=None, verbose=False, fixed_X_dims=None
):
    """
    This function runs on kernels to check the correctness of their
    implementation. It checks that the covariance function is positive definite
    for a randomly generated data set.

    :param kern: the kernel to be tested.
    :type kern: GPy.kern.Kernpart
    :param X: X input values to test the covariance function.
    :type X: ndarray
    :param X2: X2 input values to test the covariance function.
    :type X2: ndarray

    """
    pass_checks = True
    if X is None:
        X = np.random.randn(10, kern.input_dim)
        if output_ind is not None:
            X[:, output_ind] = np.random.randint(kern.output_dim, X.shape[0])
    if X2 is None:
        X2 = np.random.randn(20, kern.input_dim)
        if output_ind is not None:
            X2[:, output_ind] = np.random.randint(kern.output_dim, X2.shape[0])

    if verbose:
        print("Checking covariance function is positive definite.")
    result = Kern_check_model(kern, X=X).is_positive_semi_definite()
    if result and verbose:
        print("Check passed.")
    if not result:
        print(
            (
                "Positive definite check failed for "
                + kern.name
                + " covariance function."
            )
        )
        pass_checks = False
        assert result
        return False

    if verbose:
        print("Checking gradients of K(X, X) wrt theta.")
    result = Kern_check_dK_dtheta(kern, X=X, X2=None).checkgrad(verbose=verbose)
    if result and verbose:
        print("Check passed.")
    if not result:
        print(
            (
                "Gradient of K(X, X) wrt theta failed for "
                + kern.name
                + " covariance function. Gradient values as follows:"
            )
        )
        Kern_check_dK_dtheta(kern, X=X, X2=None).checkgrad(verbose=True)
        pass_checks = False
        assert result
        return False

    if verbose:
        print("Checking gradients of K(X, X2) wrt theta.")
    try:
        result = Kern_check_dK_dtheta(kern, X=X, X2=X2).checkgrad(verbose=verbose)
    except NotImplementedError:
        result = True
        if verbose:
            print(
                (
                    "update_gradients_full, with differing X and X2, not implemented for "
                    + kern.name
                )
            )
    if result and verbose:
        print("Check passed.")
    if not result:
        print(
            (
                "Gradient of K(X, X) wrt theta failed for "
                + kern.name
                + " covariance function. Gradient values as follows:"
            )
        )
        Kern_check_dK_dtheta(kern, X=X, X2=X2).checkgrad(verbose=True)
        pass_checks = False
        assert result
        return False

    if verbose:
        print("Checking gradients of Kdiag(X) wrt theta.")
    try:
        result = Kern_check_dKdiag_dtheta(kern, X=X).checkgrad(verbose=verbose)
    except NotImplementedError:
        result = True
        if verbose:
            print(("update_gradients_diag not implemented for " + kern.name))
    if result and verbose:
        print("Check passed.")
    if not result:
        print(
            (
                "Gradient of Kdiag(X) wrt theta failed for "
                + kern.name
                + " covariance function. Gradient values as follows:"
            )
        )
        Kern_check_dKdiag_dtheta(kern, X=X).checkgrad(verbose=True)
        pass_checks = False
        assert result
        return False

    if verbose:
        print("Checking gradients of K(X, X) wrt X.")
    try:
        testmodel = Kern_check_dK_dX(kern, X=X, X2=None)
        if fixed_X_dims is not None:
            testmodel.X[:, fixed_X_dims].fix()
        result = testmodel.checkgrad(verbose=verbose)
    except NotImplementedError:
        result = True
        if verbose:
            print(("gradients_X not implemented for " + kern.name))
    if result and verbose:
        print("Check passed.")
    if not result:
        print(
            (
                "Gradient of K(X, X) wrt X failed for "
                + kern.name
                + " covariance function. Gradient values as follows:"
            )
        )
        testmodel.checkgrad(verbose=True)
        assert result
        pass_checks = False
        return False

    if verbose:
        print("Checking gradients of K(X, X2) wrt X.")
    try:
        testmodel = Kern_check_dK_dX(kern, X=X, X2=X2)
        if fixed_X_dims is not None:
            testmodel.X[:, fixed_X_dims].fix()
        result = testmodel.checkgrad(verbose=verbose)
    except NotImplementedError:
        result = True
        if verbose:
            print(("gradients_X not implemented for " + kern.name))
    if result and verbose:
        print("Check passed.")
    if not result:
        print(
            (
                "Gradient of K(X, X2) wrt X failed for "
                + kern.name
                + " covariance function. Gradient values as follows:"
            )
        )
        testmodel.checkgrad(verbose=True)
        assert result
        pass_checks = False
        return False

    if verbose:
        print("Checking gradients of Kdiag(X) wrt X.")
    try:
        testmodel = Kern_check_dKdiag_dX(kern, X=X)
        if fixed_X_dims is not None:
            testmodel.X[:, fixed_X_dims].fix()
        result = testmodel.checkgrad(verbose=verbose)
    except NotImplementedError:
        result = True
        if verbose:
            print(("gradients_X not implemented for " + kern.name))
    if result and verbose:
        print("Check passed.")
    if not result:
        print(
            (
                "Gradient of Kdiag(X) wrt X failed for "
                + kern.name
                + " covariance function. Gradient values as follows:"
            )
        )
        Kern_check_dKdiag_dX(kern, X=X).checkgrad(verbose=True)
        pass_checks = False
        assert result
        return False

    if verbose:
        print("Checking gradients of dK(X, X2) wrt X2 with full cov in dimensions")
    try:
        testmodel = Kern_check_d2K_dXdX(kern, X=X, X2=X2)
        if fixed_X_dims is not None:
            testmodel.X[:, fixed_X_dims].fix()
        result = testmodel.checkgrad(verbose=verbose)
    except NotImplementedError:
        result = True
        if verbose:
            print(("gradients_X not implemented for " + kern.name))
    if result and verbose:
        print("Check passed.")
    if not result:
        print(
            (
                "Gradient of dK(X, X2) wrt X failed for "
                + kern.name
                + " covariance function. Gradient values as follows:"
            )
        )
        testmodel.checkgrad(verbose=True)
        assert result
        pass_checks = False
        return False

    if verbose:
        print("Checking gradients of dK(X, X) wrt X with full cov in dimensions")
    try:
        testmodel = Kern_check_d2K_dXdX(kern, X=X, X2=None)
        if fixed_X_dims is not None:
            testmodel.X[:, fixed_X_dims].fix()
        result = testmodel.checkgrad(verbose=verbose)
    except NotImplementedError:
        result = True
        if verbose:
            print(("gradients_X not implemented for " + kern.name))
    if result and verbose:
        print("Check passed.")
    if not result:
        print(
            (
                "Gradient of dK(X, X) wrt X with full cov in dimensions failed for "
                + kern.name
                + " covariance function. Gradient values as follows:"
            )
        )
        testmodel.checkgrad(verbose=True)
        assert result
        pass_checks = False
        return False

    if verbose:
        print("Checking gradients of dKdiag(X, X) wrt X with cov in dimensions")
    try:
        testmodel = Kern_check_d2Kdiag_dXdX(kern, X=X)
        if fixed_X_dims is not None:
            testmodel.X[:, fixed_X_dims].fix()
        result = testmodel.checkgrad(verbose=verbose)
    except NotImplementedError:
        result = True
        if verbose:
            print(("gradients_X not implemented for " + kern.name))
    if result and verbose:
        print("Check passed.")
    if not result:
        print(
            (
                "Gradient of dKdiag(X, X) wrt X with cov in dimensions failed for "
                + kern.name
                + " covariance function. Gradient values as follows:"
            )
        )
        testmodel.checkgrad(verbose=True)
        assert result
        pass_checks = False
        return False

    return pass_checks


class TestKernelGradientContinuous:
    def setup(self):
        self.N, self.D = 10, 5
        self.X = np.random.randn(self.N, self.D + 1)
        self.X2 = np.random.randn(self.N + 10, self.D + 1)

        continuous_kerns = ["RBF", "Linear"]
        self.kernclasses = [getattr(GPy.kern, s) for s in continuous_kerns]

    def test_MLP(self):
        self.setup()
        k = GPy.kern.MLP(self.D, ARD=True)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_Matern32(self):
        self.setup()
        k = GPy.kern.Matern32(self.D)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_Prod(self):
        self.setup()
        k = GPy.kern.Matern32(2, active_dims=[2, 3]) * GPy.kern.RBF(
            2, active_dims=[0, 4]
        ) + GPy.kern.Linear(self.D)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_Prod1(self):
        self.setup()
        k = GPy.kern.RBF(self.D) * GPy.kern.Linear(self.D)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_Prod2(self):
        self.setup()
        k = GPy.kern.RBF(2, active_dims=[0, 4]) * GPy.kern.Linear(self.D)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_Prod3(self):
        self.setup()
        k = GPy.kern.RBF(self.D) * GPy.kern.Linear(self.D) * GPy.kern.Bias(self.D)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_Prod4(self):
        self.setup()
        k = (
            GPy.kern.RBF(2, active_dims=[0, 4])
            * GPy.kern.Linear(self.D)
            * GPy.kern.Matern32(2, active_dims=[0, 1])
        )
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_Add(self):
        self.setup()
        k = (
            GPy.kern.Matern32(2, active_dims=[2, 3])
            + GPy.kern.RBF(2, active_dims=[0, 4])
            + GPy.kern.Linear(self.D)
        )
        k += (
            GPy.kern.Matern32(2, active_dims=[2, 3])
            + GPy.kern.RBF(2, active_dims=[0, 4])
            + GPy.kern.Linear(self.D)
        )
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_Add_dims(self):
        self.setup()
        k = (
            GPy.kern.Matern32(2, active_dims=[2, self.D])
            + GPy.kern.RBF(2, active_dims=[0, 4])
            + GPy.kern.Linear(self.D)
        )
        k.randomize()
        # with pytest.raises(IndexError):
        self.X[:, : self.D]
        k = (
            GPy.kern.Matern32(2, active_dims=[2, self.D - 1])
            + GPy.kern.RBF(2, active_dims=[0, 4])
            + GPy.kern.Linear(self.D)
        )
        k.randomize()
        # assert it runs:
        try:
            k.K(self.X)
        except AssertionError:
            raise AssertionError("k.K(X) should run on self.D-1 dimension")

    def test_Matern52(self):
        self.setup()
        k = GPy.kern.Matern52(self.D)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_RBF(self):
        self.setup()
        k = GPy.kern.RBF(self.D - 1, ARD=True)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_OU(self):
        self.setup()
        k = GPy.kern.OU(self.D - 1, ARD=True)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_Cosine(self):
        self.setup()
        # Don't test Cosine directly as it fails positive definite test.
        k = GPy.kern.RBF(self.D - 1, ARD=False) * GPy.kern.Cosine(self.D - 1, ARD=True)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_ExpQuadCosine(self):
        self.setup()
        k = GPy.kern.ExpQuadCosine(self.D - 1, ARD=True)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_Sinc(self):
        self.setup()
        k = GPy.kern.Sinc(self.D - 1, ARD=True)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_RatQuad(self):
        self.setup()
        k = GPy.kern.RatQuad(self.D - 1, ARD=True)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_ExpQuad(self):
        self.setup()
        k = GPy.kern.ExpQuad(self.D - 1, ARD=True)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_integral(self):
        self.setup()
        k = GPy.kern.Integral(1)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_multidimensional_integral_limits(self):
        self.setup()
        k = GPy.kern.Multidimensional_Integral_Limits(2)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_integral_limits(self):
        self.setup()
        k = GPy.kern.Integral_Limits(2)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_Linear(self):
        self.setup()
        k = GPy.kern.Linear(self.D)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_LinearFull(self):
        self.setup()
        k = GPy.kern.LinearFull(self.D, self.D - 1)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_Fixed(self):
        self.setup()
        cov = np.dot(self.X, self.X.T)
        X = np.arange(self.N).reshape(self.N, 1)
        k = GPy.kern.Fixed(1, cov)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=X, X2=None, verbose=verbose)

    def test_Poly(self):
        self.setup()
        k = GPy.kern.Poly(self.D, order=5)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_WhiteHeteroscedastic(self):
        self.setup()
        k = GPy.kern.WhiteHeteroscedastic(self.D, self.X.shape[0])
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_standard_periodic(self):
        self.setup()
        k = GPy.kern.StdPeriodic(self.D)
        k.randomize()
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_symmetric_even(self):
        self.setup()
        k_base = GPy.kern.Linear(1) + GPy.kern.RBF(1)
        transform = -np.array([[1.0]])
        k = GPy.kern.Symmetric(k_base, transform, "even")
        assert check_kernel_gradient_functions(k)

    def test_symmetric_odd(self):
        self.setup()
        k_base = GPy.kern.Linear(1) + GPy.kern.RBF(1)
        transform = -np.array([[1.0]])
        k = GPy.kern.Symmetric(k_base, transform, "odd")
        assert check_kernel_gradient_functions(k)

    def test_MultioutputKern(self):
        self.setup()
        k1 = GPy.kern.RBF(self.D, ARD=True)
        k1.randomize()
        k2 = GPy.kern.RBF(self.D, ARD=True)
        k2.randomize()

        k = GPy.kern.MultioutputKern([k1, k2])
        Xt, _, _ = GPy.util.multioutput.build_XY([self.X, self.X])
        X2t, _, _ = GPy.util.multioutput.build_XY([self.X2, self.X2])
        assert check_kernel_gradient_functions(
            k, X=Xt, X2=X2t, verbose=verbose, fixed_X_dims=-1
        )

    def test_Precomputed(self):
        self.setup()
        Xall = np.concatenate([self.X, self.X2])
        cov = np.dot(Xall, Xall.T)
        X = np.arange(self.N).reshape(self.N, 1)
        X2 = np.arange(self.N, 2 * self.N + 10).reshape(self.N + 10, 1)
        k = GPy.kern.Precomputed(1, cov)
        k.randomize()
        assert check_kernel_gradient_functions(
            k, X=X, X2=X2, verbose=verbose, fixed_X_dims=[0]
        )

    def test_basis_func_linear_slope(self):
        self.setup()
        start_stop = np.random.uniform(
            self.X.min(0), self.X.max(0), (4, self.X.shape[1])
        ).T
        start_stop.sort(axis=1)
        ks = []
        for i in range(start_stop.shape[0]):
            start, stop = np.split(start_stop[i], 2)
            ks.append(
                GPy.kern.LinearSlopeBasisFuncKernel(
                    1, start, stop, ARD=i % 2 == 0, active_dims=[i]
                )
            )
        k = GPy.kern.Add(ks)
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_basis_func_changepoint(self):
        self.setup()
        points = np.random.uniform(self.X.min(0), self.X.max(0), (self.X.shape[1]))
        ks = []
        for i in range(points.shape[0]):
            ks.append(
                GPy.kern.ChangePointBasisFuncKernel(
                    1, points[i], ARD=i % 2 == 0, active_dims=[i]
                )
            )
        k = GPy.kern.Add(ks)
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_basis_func_poly(self):
        self.setup()
        ks = []
        for i in range(self.X.shape[1]):
            ks.append(
                GPy.kern.PolynomialBasisFuncKernel(
                    1, 5, ARD=i % 2 == 0, active_dims=[i]
                )
            )
        k = GPy.kern.Add(ks)
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)

    def test_basis_func_domain(self):
        self.setup()
        start_stop = np.random.uniform(
            self.X.min(0), self.X.max(0), (4, self.X.shape[1])
        ).T
        start_stop.sort(axis=1)
        ks = []
        for i in range(start_stop.shape[0]):
            start, stop = np.split(start_stop[i], 2)
            ks.append(
                GPy.kern.DomainKernel(1, start, stop, ARD=i % 2 == 0, active_dims=[i])
            )
        k = GPy.kern.Add(ks)
        assert check_kernel_gradient_functions(k, X=self.X, X2=self.X2, verbose=verbose)


class TestKernelMiscellaneous:
    def setup(self):
        N, D = 100, 10
        self.X = np.linspace(-np.pi, +np.pi, N)[:, None] * np.random.uniform(-10, 10, D)
        self.rbf = GPy.kern.RBF(2, active_dims=np.arange(0, 4, 2))
        self.rbf.randomize()
        self.linear = GPy.kern.Linear(2, active_dims=(3, 9))
        self.linear.randomize()
        self.matern = GPy.kern.Matern32(3, active_dims=np.array([1, 7, 9]))
        self.matern.randomize()
        self.sumkern = self.rbf + self.linear
        self.sumkern += self.matern
        # self.sumkern.randomize()

    def test_which_parts(self):
        self.setup()
        assert np.allclose(
            self.sumkern.K(self.X, which_parts=[self.linear, self.matern]),
            self.linear.K(self.X) + self.matern.K(self.X),
        )
        assert np.allclose(
            self.sumkern.K(self.X, which_parts=[self.linear, self.rbf]),
            self.linear.K(self.X) + self.rbf.K(self.X),
        )
        assert np.allclose(
            self.sumkern.K(self.X, which_parts=self.sumkern.parts[0]),
            self.rbf.K(self.X),
        )

    def test_active_dims(self):
        self.setup()
        np.testing.assert_array_equal(self.sumkern.active_dims, [0, 1, 2, 3, 7, 9])
        np.testing.assert_array_equal(self.sumkern._all_dims_active, range(10))
        tmp = self.linear + self.rbf
        np.testing.assert_array_equal(tmp.active_dims, [0, 2, 3, 9])
        np.testing.assert_array_equal(tmp._all_dims_active, range(10))
        tmp = self.matern + self.rbf
        np.testing.assert_array_equal(tmp.active_dims, [0, 1, 2, 7, 9])
        np.testing.assert_array_equal(tmp._all_dims_active, range(10))
        tmp = self.matern + self.rbf * self.linear
        np.testing.assert_array_equal(tmp.active_dims, [0, 1, 2, 3, 7, 9])
        np.testing.assert_array_equal(tmp._all_dims_active, range(10))
        tmp = self.matern + self.rbf + self.linear
        np.testing.assert_array_equal(tmp.active_dims, [0, 1, 2, 3, 7, 9])
        np.testing.assert_array_equal(tmp._all_dims_active, range(10))
        tmp = self.matern * self.rbf * self.linear
        np.testing.assert_array_equal(tmp.active_dims, [0, 1, 2, 3, 7, 9])
        np.testing.assert_array_equal(tmp._all_dims_active, range(10))


class TestKernelNonContinuous:
    def setup(self):
        N0 = 3
        N1 = 9
        N2 = 4
        N = N0 + N1 + N2
        self.D = 3
        self.X = np.random.randn(N, self.D + 1)
        indices = np.random.random_integers(0, 2, size=N)
        self.X[indices == 0, -1] = 0
        self.X[indices == 1, -1] = 1
        self.X[indices == 2, -1] = 2
        # self.X = self.X[self.X[:, -1].argsort(), :]
        self.X2 = np.random.randn((N0 + N1) * 2, self.D + 1)
        self.X2[: (N0 * 2), -1] = 0
        self.X2[(N0 * 2) :, -1] = 1

    def test_IndependentOutputs(self):
        self.setup()
        k = [
            GPy.kern.RBF(1, active_dims=[1], name="rbf1"),
            GPy.kern.RBF(self.D, active_dims=range(self.D), name="rbf012"),
            GPy.kern.RBF(2, active_dims=[0, 2], name="rbf02"),
        ]
        kern = GPy.kern.IndependentOutputs(k, -1, name="ind_split")
        np.testing.assert_array_equal(kern.active_dims, [-1, 0, 1, 2])
        np.testing.assert_array_equal(kern._all_dims_active, [0, 1, 2, -1])

    def test_IndependendGradients(self):
        self.setup()
        k = GPy.kern.RBF(self.D, active_dims=range(self.D))
        kern = GPy.kern.IndependentOutputs(k, -1, "ind_single")
        assert check_kernel_gradient_functions(
            kern, X=self.X, X2=self.X2, verbose=verbose, fixed_X_dims=-1
        )
        k = [
            GPy.kern.RBF(1, active_dims=[1], name="rbf1"),
            GPy.kern.RBF(self.D, active_dims=range(self.D), name="rbf012"),
            GPy.kern.RBF(2, active_dims=[0, 2], name="rbf02"),
        ]
        kern = GPy.kern.IndependentOutputs(k, -1, name="ind_split")
        assert check_kernel_gradient_functions(
            kern, X=self.X, X2=self.X2, verbose=verbose, fixed_X_dims=-1
        )

    def test_Hierarchical(self):
        self.setup()
        k = [
            GPy.kern.RBF(2, active_dims=[0, 2], name="rbf1"),
            GPy.kern.RBF(2, active_dims=[0, 2], name="rbf2"),
        ]
        kern = GPy.kern.IndependentOutputs(k, -1, name="ind_split")
        np.testing.assert_array_equal(kern.active_dims, [-1, 0, 2])
        np.testing.assert_array_equal(kern._all_dims_active, [0, 1, 2, -1])

    def test_Hierarchical_gradients(self):
        self.setup()
        k = [
            GPy.kern.RBF(2, active_dims=[0, 2], name="rbf1"),
            GPy.kern.RBF(2, active_dims=[0, 2], name="rbf2"),
        ]
        kern = GPy.kern.IndependentOutputs(k, -1, name="ind_split")
        assert check_kernel_gradient_functions(
            kern, X=self.X, X2=self.X2, verbose=verbose, fixed_X_dims=-1
        )

    def test_ODE_UY(self):
        self.setup()
        kern = GPy.kern.ODE_UY(2, active_dims=[0, self.D])
        X = self.X[self.X[:, -1] != 2]
        X2 = self.X2[self.X2[:, -1] != 2]
        assert check_kernel_gradient_functions(
            kern, X=X, X2=X2, verbose=verbose, fixed_X_dims=-1
        )

    def test_Coregionalize(self):
        self.setup()
        kern = GPy.kern.Coregionalize(1, output_dim=3, active_dims=[-1])
        assert check_kernel_gradient_functions(
            kern, X=self.X, X2=self.X2, verbose=verbose, fixed_X_dims=-1
        )


@pytest.mark.skipif(
    not cython_coregionalize_working,
    reason="Cython coregionalize module has not been built on this machine",
)
class TestCoregionalizeCython:
    """
    Make sure that the coregionalize kernel work with and without cython enabled
    """

    def setup(self):
        self.k = GPy.kern.Coregionalize(1, output_dim=12)
        self.N1, self.N2 = 100, 200
        self.X = np.random.randint(0, 12, (self.N1, 1))
        self.X2 = np.random.randint(0, 12, (self.N2, 1))

    def test_sym(self):
        self.setup()
        dL_dK = np.random.randn(self.N1, self.N1)
        K_cython = self.k._K_cython(self.X)
        self.k.update_gradients_full(dL_dK, self.X)
        grads_cython = self.k.gradient.copy()

        K_numpy = self.k._K_numpy(self.X)
        # Nasty hack to ensure the numpy version is used for update_gradients
        # If this test is running, cython is working, so override the cython
        # function with the numpy function
        _gradient_reduce_cython = self.k._gradient_reduce_cython
        self.k._gradient_reduce_cython = self.k._gradient_reduce_numpy
        self.k.update_gradients_full(dL_dK, self.X)
        # Undo hack
        self.k._gradient_reduce_cython = _gradient_reduce_cython
        grads_numpy = self.k.gradient.copy()

        assert np.allclose(K_numpy, K_cython)
        assert np.allclose(grads_numpy, grads_cython)

    def test_nonsym(self):
        self.setup()
        dL_dK = np.random.randn(self.N1, self.N2)
        K_cython = self.k._K_cython(self.X, self.X2)
        self.k.gradient = 0.0
        self.k.update_gradients_full(dL_dK, self.X, self.X2)
        grads_cython = self.k.gradient.copy()

        K_numpy = self.k._K_numpy(self.X, self.X2)
        self.k.gradient = 0.0
        # Same hack as in test_sym (Line 639)
        _gradient_reduce_cython = self.k._gradient_reduce_cython
        self.k._gradient_reduce_cython = self.k._gradient_reduce_numpy
        self.k.update_gradients_full(dL_dK, self.X, self.X2)
        # Undo hack
        self.k._gradient_reduce_cython = _gradient_reduce_cython
        grads_numpy = self.k.gradient.copy()

        assert np.allclose(K_numpy, K_cython)
        assert np.allclose(grads_numpy, grads_cython)


class TestKernelProductWithZeroValues:
    def setup(self):
        self.X = np.array([[0, 1], [1, 0]])
        self.k = GPy.kern.Linear(2) * GPy.kern.Bias(2)

    def test_zero_valued_kernel_full(self):
        self.setup()
        self.k.update_gradients_full(1, self.X)
        assert not np.isnan(
            self.k["linear.variances"].gradient
        ), "Gradient resulted in NaN"

    def test_zero_valued_kernel_gradients_X(self):
        self.setup()
        target = self.k.gradients_X(1, self.X)
        assert not np.any(np.isnan(target)), "Gradient resulted in NaN"


class TestKernelPsiStatisticsGradient:
    def setup(self):
        from GPy.core.parameterization.variational import NormalPosterior

        N, M, Q = 100, 20, 3

        X = np.random.randn(N, Q)
        X_var = np.random.rand(N, Q) + 0.01
        self.Z = np.random.randn(M, Q)
        self.qX = NormalPosterior(X, X_var)

        self.w1 = np.random.randn(N)
        self.w2 = np.random.randn(N, M)
        self.w3 = np.random.randn(M, M)
        self.w3 = self.w3  # +self.w3.T
        self.w3n = np.random.randn(N, M, M)
        self.w3n = self.w3n + np.swapaxes(self.w3n, 1, 2)

    def test_kernels(self):
        self.setup()
        from GPy.kern import RBF, Linear, MLP, Bias, White

        Q = self.Z.shape[1]
        kernels = [
            RBF(Q, ARD=True),
            Linear(Q, ARD=True),
            MLP(Q, ARD=True),
            RBF(Q, ARD=True) + Linear(Q, ARD=True) + Bias(Q) + White(Q),
            RBF(Q, ARD=True) + Bias(Q) + White(Q),
            Linear(Q, ARD=True) + Bias(Q) + White(Q),
        ]

        for k in kernels:
            k.randomize()
            self._test_kernel_param(k)
            self._test_Z(k)
            self._test_qX(k)
            self._test_kernel_param(k, psi2n=True)
            self._test_Z(k, psi2n=True)
            self._test_qX(k, psi2n=True)

    def _test_kernel_param(self, kernel, psi2n=False):
        def f(p):
            kernel.param_array[:] = p
            psi0 = kernel.psi0(self.Z, self.qX)
            psi1 = kernel.psi1(self.Z, self.qX)
            if not psi2n:
                psi2 = kernel.psi2(self.Z, self.qX)
                return (
                    (self.w1 * psi0).sum()
                    + (self.w2 * psi1).sum()
                    + (self.w3 * psi2).sum()
                )
            else:
                psi2 = kernel.psi2n(self.Z, self.qX)
                return (
                    (self.w1 * psi0).sum()
                    + (self.w2 * psi1).sum()
                    + (self.w3n * psi2).sum()
                )

        def df(p):
            kernel.param_array[:] = p
            kernel.update_gradients_expectations(
                self.w1, self.w2, self.w3 if not psi2n else self.w3n, self.Z, self.qX
            )
            return kernel.gradient.copy()

        from GPy.models import GradientChecker

        m = GradientChecker(f, df, kernel.param_array.copy())
        m.checkgrad(verbose=1)
        assert m.checkgrad()

    def _test_Z(self, kernel, psi2n=False):
        def f(p):
            psi0 = kernel.psi0(p, self.qX)
            psi1 = kernel.psi1(p, self.qX)
            psi2 = kernel.psi2(p, self.qX)
            if not psi2n:
                psi2 = kernel.psi2(p, self.qX)
                return (
                    (self.w1 * psi0).sum()
                    + (self.w2 * psi1).sum()
                    + (self.w3 * psi2).sum()
                )
            else:
                psi2 = kernel.psi2n(p, self.qX)
                return (
                    (self.w1 * psi0).sum()
                    + (self.w2 * psi1).sum()
                    + (self.w3n * psi2).sum()
                )

        def df(p):
            return kernel.gradients_Z_expectations(
                self.w1, self.w2, self.w3 if not psi2n else self.w3n, p, self.qX
            )

        from GPy.models import GradientChecker

        m = GradientChecker(f, df, self.Z.copy())
        assert m.checkgrad()

    def _test_qX(self, kernel, psi2n=False):
        def f(p):
            self.qX.param_array[:] = p
            self.qX._trigger_params_changed()
            psi0 = kernel.psi0(self.Z, self.qX)
            psi1 = kernel.psi1(self.Z, self.qX)
            if not psi2n:
                psi2 = kernel.psi2(self.Z, self.qX)
                return (
                    (self.w1 * psi0).sum()
                    + (self.w2 * psi1).sum()
                    + (self.w3 * psi2).sum()
                )
            else:
                psi2 = kernel.psi2n(self.Z, self.qX)
                return (
                    (self.w1 * psi0).sum()
                    + (self.w2 * psi1).sum()
                    + (self.w3n * psi2).sum()
                )

        def df(p):
            self.qX.param_array[:] = p
            self.qX._trigger_params_changed()
            grad = kernel.gradients_qX_expectations(
                self.w1, self.w2, self.w3 if not psi2n else self.w3n, self.Z, self.qX
            )
            self.qX.set_gradients(grad)
            return self.qX.gradient.copy()

        from GPy.models import GradientChecker

        m = GradientChecker(f, df, self.qX.param_array.copy())
        assert m.checkgrad()
