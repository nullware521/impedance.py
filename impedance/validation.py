import numpy as np
from impedance.models.circuits.fitting import rmse
from impedance.models.circuits.elements import circuit_elements, K  # noqa


def linKK(f, Z, c=0.85, max_M=50, fit_type='real', add_cap=False):
    """ A method for implementing the Lin-KK test for validating linearity [1]

    Parameters
    ----------
    f: np.ndarray
        measured frequencies
    Z: np.ndarray of complex numbers
        measured impedances
    c: np.float
        cutoff for mu
    max_M: int
        the maximum number of RC elements
    fit_type: str
        selects which components of data are fit ('real', 'imag', or
        'complex')
    add_cap: bool
        option to add a serial capacitance that helps validate data with no
        low-frequency intercept

    Returns
    -------
    M: int
        number of RC elements used
    mu: np.float
        under- or over-fitting measure
    Z_fit: np.ndarray of complex numbers
        impedance of fit at input frequencies
    resids_real: np.ndarray
        real component of the residuals of the fit at input frequencies
    resids_imag: np.ndarray
        imaginary component of the residuals of the fit at input frequencies


    Notes
    -----

    The lin-KK method from Schönleber et al. [1] is a quick test for checking
    the
    validity of EIS data. The validity of an impedance spectrum is analyzed by
    its reproducibility by a Kramers-Kronig (KK) compliant equivalent circuit.
    In particular, the model used in the lin-KK test is an ohmic resistor,
    :math:`R_{Ohm}`, and :math:`M` RC elements.

    .. math::

        \\hat Z = R_{Ohm} + \\sum_{k=1}^{M} \\frac{R_k}{1 + j \\omega \\tau_k}

    The :math:`M` time constants, :math:`\\tau_k`, are distributed
    logarithmically,

    .. math::
        \\tau_1 = \\frac{1}{\\omega_{max}} ; \\tau_M = \\frac{1}{\\omega_{min}}
        ; \\tau_k = 10^{\\log{(\\tau_{min}) + \\frac{k-1}{M-1}\\log{{(
            \\frac{\\tau_{max}}{\\tau_{min}}}})}}

    and are not fit during the test (only :math:`R_{Ohm}` and :math:`R_{k}`
    are free parameters).

    In order to prevent under- or over-fitting, Schönleber et al. propose using
    the ratio of positive resistor mass to negative resistor mass as a metric
    for finding the optimal number of RC elements.

    .. math::

        \\mu = 1 - \\frac{\\sum_{R_k \\ge 0} |R_k|}{\\sum_{R_k < 0} |R_k|}

    The argument :code:`c` defines the cutoff value for :math:`\\mu`. The
    algorithm starts at :code:`M = 3` and iterates up to :code:`max_M` until a
    :math:`\\mu < c` is reached. The default of 0.85 is simply a heuristic
    value based off of the experience of Schönleber et al., but a lower value
    may give better results.

    If the argument :code:`c` is :code:`None`, then the automatic determination
    of RC elements is turned off and the solution is calculated for
    :code:`max_M` RC elements. This manual mode should be used with caution as
    under- and over-fitting should be avoided.

    [1] Schönleber, M. et al. A Method for Improving the Robustness of
    linear Kramers-Kronig Validity Tests. Electrochimica Acta 131, 20–27 (2014)
    `doi: 10.1016/j.electacta.2014.01.034
    <https://doi.org/10.1016/j.electacta.2014.01.034>`_.

    """

    if c is not None:
        M = 0
        mu = 1
        while mu > c and M <= max_M:
            M += 1
            ts = get_tc_distribution(f, M)
            p_values, mu = fit_linKK(f, ts, M, Z, fit_type, add_cap)

            if M % 10 == 0:
                print(M, mu, rmse(eval_linKK(p_values, ts, f), Z))
    else:
        M = max_M
        ts = get_tc_distribution(f, M)
        p_values, mu = fit_linKK(f, ts, M, Z, fit_type, add_cap)

    Z_fit = eval_linKK(p_values, ts, f)
    resids_real = residuals_linKK(p_values, ts, Z, f, residuals='real')
    resids_imag = residuals_linKK(p_values, ts, Z, f, residuals='imag')
    return M, mu, Z_fit, resids_real, resids_imag


def get_tc_distribution(f, M):
    """ Returns the distribution of time constants for the linKK method """

    t_max = 1/(2 * np.pi * np.min(f))
    t_min = 1/(2 * np.pi * np.max(f))
    ts = np.zeros(shape=(M,))
    ts[0] = t_min
    ts[-1] = t_max
    if M > 1:
        for k in range(2, M):
            ts[k-1] = 10**(np.log10(t_min) +
                           ((k-1)/(M-1))*np.log10(t_max/t_min))
    return ts


def fit_linKK(f, ts, M, Z, fit_type='real', add_cap=False):
    """ Fits the linKK model using linear regression

    Parameters
    ----------
    f: np.ndarray
        measured frequencies
    ts: np.ndarray
        logarithmically spaced time constants of RC elements
    M: int
        the number of RC elements
    Z: np.ndarray of complex numbers
        measured impedances
    fit_type: str
        selects which components of data are fit ('real', 'imag', or
        'complex')
    add_cap: bool
        option to add a serial capacitance that helps validate data with no
        low-frequency intercept

    Returns
    -------
    p_values: np.ndarray
        values of fit R_k in RC elements
    mu: np.float
        under- or over-fitting measure

    Notes
    -----
    Solving this as a system of equations that's linear wrt Rk, where Ax~=b
    and we are trying to minimize r = ||Ax - b||**2. Fitting to the real or
    imaginary parts, b = Re[Z] or Im[Z], respectively, and Ax is our model
    fit, Z_hat. Z_hat = R_o + sum[k:1, M](R_k / (1 + j * w * tau_k). x is an
    (M+1) x 1 matrix where the first row contains R_o and subsequent rows
    contain R_k values. A is an N x (M+1) matrix, where N is the number of
    data points, of independent variable values. Ex, fitting the real part of
    data, the first column contains values of 1 / |Z|, the second column
    contains Re[1 / (1 + j * w * tau_1)], the third contains
    Re[1 / (1 + j * w *tau_k)] and so on. Fitting the complex values is
    different since r = ||A'x - b'||**2 + ||A''x - b'||**2 according to Eq 14
    of Schonleber [1], so finding the coefficients is done "manually" with
    matrix manipulations instead of using numpy.linalg.pinv(A)

    [1] Schönleber, M. et al. A Method for Improving the Robustness of
    linear Kramers-Kronig Validity Tests. Electrochimica Acta 131, 20–27 (2014)
    `doi: 10.1016/j.electacta.2014.01.034
    <https://doi.org/10.1016/j.electacta.2014.01.034>`_.
    """

    w = 2 * np.pi * f

    # Fitting model has M RC elements plus 1 series resistance and 1 series
    # inductance
    a_re = np.zeros((f.size, M+2))
    a_im = np.zeros((f.size, M+2))

    if add_cap:
        a_re = np.zeros((f.size, M+3))
        a_im = np.zeros((f.size, M+3))

        # Column for series capacitance. Real part = 0.
        a_im[:, -2] = - 1 / (w * np.abs(Z))

    # Column for series resistance, R_o in model. Imaginary part = 0.
    a_re[:, 0] = 1 / np.abs(Z)

    # Column for series inductance to capture inevitable contributions from
    # the measurement system. Real part = 0.
    a_im[:, -1] = w / np.abs(Z)

    # Columns for series RC elements
    for i, tau in enumerate(ts):
        a_re[:, i+1] = K([1, tau], f).real / np.abs(Z)
        a_im[:, i+1] = K([1, tau], f).imag / np.abs(Z)

    if fit_type == 'real':
        p_values = np.linalg.pinv(a_re).dot(Z.real / np.abs(Z))

        # After fitting real part, need to use imaginary component of fit to
        # find values of series inductance and capacitance
        a_im = np.zeros((f.size, 2))
        a_im[:, -1] = w / np.abs(Z)
        if add_cap:
            a_im[:, -2] = -1 / (w * np.abs(Z))
            p_values[-2] = 1e-18  # nullifies series C without dividing by 0

        Z_fit_re = eval_linKK(p_values, ts, f)
        coefs = np.linalg.pinv(a_im).dot((Z.imag - Z_fit_re.imag) / np. abs(Z))

        if add_cap:
            p_values[-2:] = coefs
        else:
            p_values[-1] = coefs[-1]
    elif fit_type == 'imag':
        p_values = np.linalg.pinv(a_im).dot(Z.imag / np.abs(Z))

        # Calculates real part of impedance from fitting to imaginary parts
        # without ohmic resistance, i.e. only the real parts of series RC
        # elements.
        z_re = eval_linKK(p_values, ts, f)

        # Weighting used in Boukamp et al - "A Linear Kronig-Kramers
        # Transform for Immittance Data Validation" 1995, J. Electrochem
        # Soc. 142 (6)
        ws = 1 / (Z.real**2 + Z.imag**2)

        # Finds ohmic resistance for imaginary part fit according to Eq 7
        # of Boukamp et al.
        p_values[0] = np.sum(ws * (Z.real - z_re.real)) / np.sum(ws)
    elif fit_type == 'complex':
        x = np.linalg.inv(a_re.T.dot(a_re) + a_im.T.dot(a_im))
        y = a_re.T.dot(Z.real / np.abs(Z)) + a_im.T.dot(Z.imag / np.abs(Z))
        p_values = x.dot(y)
    else:
        raise ValueError("Invalid choice of fit_type, please choose from "
                         "\'real\', \'imag\', or \'complex\'")

    if add_cap:
        mu = calc_mu(p_values[:-2])
    else:
        mu = calc_mu(p_values[:-1])

    return p_values, mu


def eval_linKK(Rs, ts, f):
    """ Builds a circuit of RC elements to be used in LinKK """
    circuit_string = 's([R({},{}),'.format([Rs[0]], f.tolist())

    for (Rk, tk) in zip(Rs[1:], ts):
        circuit_string += 'K({},{}),'.format([Rk, tk], f.tolist())

    circuit_string += 'L({},{}),'.format([Rs[-1]], f.tolist())
    if Rs.size == (ts.size + 3):
        circuit_string += 'C({},{}),'.format([1/Rs[-2]], f.tolist())

    circuit_string = circuit_string.strip(',')
    circuit_string += '])'

    return eval(circuit_string, circuit_elements)


def residuals_linKK(Rs, ts, Z, f, residuals='real'):
    """ Calculates the residual between the data and a LinKK fit """

    err = (Z - eval_linKK(Rs, ts, f))/np.abs(Z)

    if residuals == 'real':
        return err.real
    elif residuals == 'imag':
        return err.imag
    elif residuals == 'both':
        z1d = np.zeros(Z.size*2, dtype=np.float64)
        z1d[0:z1d.size:2] = err.real
        z1d[1:z1d.size:2] = err.imag

        return z1d


def calc_mu(Rs):
    """ Calculates mu for use in LinKK """

    neg_sum = sum(abs(x) for x in Rs if x < 0)
    pos_sum = sum(abs(x) for x in Rs if x >= 0)

    return 1 - neg_sum/pos_sum
