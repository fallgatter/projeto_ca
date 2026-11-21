from math import copysign, sqrt


WINDOW_MINUTES = 5


def persistent_error(counts):
    """Return the rate deviation beyond the tolerance for sparse counts."""
    observed = sum(count for count, _ in counts)
    expected = sum(target for _, target in counts)
    tolerance = 2*sqrt(max(1., expected))
    difference = observed-expected
    excess = copysign(max(0., abs(difference)-tolerance), difference)
    return observed, expected, tolerance, 60*excess/len(counts)
