from __future__ import division
from __future__ import print_function

import numpy as np
from sklearn.utils import check_array
from sklearn.utils.validation import check_is_fitted
from sklearn.utils import column_or_1d
from .base import Base
from utils.utilities import check_parameter
from numpy import percentile


class HBOS(Base):
    """Histogram- based outlier detection (HBOS) is an efficient unsupervised
    method. It assumes the feature independence and calculates the degree
    of outlyingness by building histograms. See :cite:`goldstein2012histogram`
    for details.

    Parameters
    ----------
    n_bins : int, optional (default=10)
        The number of bins.

    alpha : float in (0, 1), optional (default=0.1)
        The regularizer for preventing overflow.

    tol : float in (0, 1), optional (default=0.1)
        The parameter to decide the flexibility while dealing
        the samples falling outside the bins.

    contamination : float in (0., 0.5), optional (default=0.1)
        The amount of contamination of the data set,
        i.e. the proportion of outliers in the data set. Used when fitting to
        define the threshold on the decision function.

    Attributes
    ----------
    bin_edges_ : numpy array of shape (n_bins + 1, n_features )
        The edges of the bins.

    hist_ : numpy array of shape (n_bins, n_features)
        The density of each histogram.

    decision_scores_ : numpy array of shape (n_samples,)
        The outlier scores of the training data.
        The higher, the more abnormal. Outliers tend to have higher
        scores. This value is available once the detector is fitted.

    threshold_ : float
        The threshold is based on ``contamination``. It is the
        ``n_samples * contamination`` most abnormal samples in
        ``decision_scores_``. The threshold is calculated for generating
        binary outlier labels.

    labels_ : int, either 0 or 1
        The binary labels of the training data. 0 stands for inliers
        and 1 for outliers/anomalies. It is generated by applying
        ``threshold_`` on ``decision_scores_``.
    """

    def __init__(self, n_bins=10, alpha=0.1, tol=0.5, contamination=0.1):
        super(HBOS, self).__init__()
        self.n_bins = n_bins
        self.alpha = alpha
        self.tol = tol
        self.contamination=contamination
        self.threshold = None

        check_parameter(alpha, 0, 1, param_name='alpha')
        check_parameter(tol, 0, 1, param_name='tol')

    def fit(self, X, y=None):
        """Fit detector

        Parameters
        ----------
        X : dataframe of shape (n_samples, n_features)
            The input samples.
        """
        # validate inputs X and y (optional)
        X = check_array(X)

        n_samples, n_features = X.shape[0], X.shape[1]
        self.hist_ = np.zeros([self.n_bins, n_features])
        self.bin_edges_ = np.zeros([self.n_bins + 1, n_features])

        # build the histograms for all dimensions
        for i in range(n_features):
            self.hist_[:, i], self.bin_edges_[:, i] = \
                np.histogram(X[:, i], bins=self.n_bins, density=True)
            # the sum of (width * height) should equal to 1
            assert (np.isclose(1, np.sum(
                self.hist_[:, i] * np.diff(self.bin_edges_[:, i])), atol=0.1))

        # outlier_scores = self._calculate_outlier_scores(X)
        outlier_scores = _calculate_outlier_scores(X, self.bin_edges_,
                                                   self.hist_,
                                                   self.n_bins,
                                                   self.alpha, self.tol)

        # invert decision_scores_. Outliers comes with higher outlier scores
        self.decision_scores_ = invert_order(np.sum(outlier_scores, axis=1))
        self._process_decision_scores()
        return self

    def _process_decision_scores(self):
        """Internal function to calculate key attributes:
        - threshold_: used to decide the binary label
        - labels_: binary labels of training data
        Returns
        -------
        self
        """

        self.threshold_ = percentile(self.decision_scores_,
                                     100 * (1 - self.contamination))
        self.labels_ = (self.decision_scores_ > self.threshold_).astype(
            'int').ravel()

        # calculate for predict_proba()

        self._mu = np.mean(self.decision_scores_)
        self._sigma = np.std(self.decision_scores_)

        return self

    def decision_function(self, X):
        """Predict raw anomaly score of X using the fitted detector.

        The anomaly score of an input sample is computed based on different
        detector algorithms. For consistency, outliers are assigned with
        larger anomaly scores.

        Parameters
        ----------
        X : dataframe of shape (n_samples, n_features)
            The training input samples. Sparse matrices are accepted only
            if they are supported by the base estimator.
        Returns
        -------
        anomaly_scores : numpy array of shape (n_samples,)
            The anomaly score of the input samples.
        """
        check_is_fitted(self, ['hist_', 'bin_edges_'])
        X = X.to_numpy()
        X = check_array(X)
        outlier_scores = _calculate_outlier_scores(X, self.bin_edges_,
                                                   self.hist_,
                                                   self.n_bins,
                                                   self.alpha, self.tol)
        return invert_order(np.sum(outlier_scores, axis=1))

    def predict(self, X):
        """Return outliers with -1 and inliers with 1, with the outlierness score calculated from the `decision_function(X)',
        and the threshold `contamination'.
        Parameters
        ----------
        X : dataframe of shape (n_samples, n_features)
            The input samples.

        Returns
        -------
        ranking : numpy array of shape (n_samples,)
            The outlierness of the input samples.
        """
        anomalies = self.decision_function(X)
        ranking = np.sort(anomalies)
        threshold = ranking[int((1-self.contamination)*len(ranking))]
        self.threshold = threshold
        mask = (anomalies>=threshold)
        ranking[mask]=-1
        ranking[np.logical_not(mask)]=1
        return ranking


def _calculate_outlier_scores(X, bin_edges, hist, n_bins, alpha,
                              tol):  # pragma: no cover
    """The internal function to calculate the outlier scores based on
    the bins and histograms constructed with the training data. The program
    is optimized through numba. It is excluded from coverage test for
    eliminating the redundancy.

    Parameters
    ----------
    X : numpy array of shape (n_samples, n_features)
        The input samples.

    bin_edges : numpy array of shape (n_bins + 1, n_features )
        The edges of the bins.

    hist : numpy array of shape (n_bins, n_features)
        The density of each histogram.

    n_bins : int, optional (default=10)
        The number of bins.

    alpha : float in (0, 1), optional (default=0.1)
        The regularizer for preventing overflow.

    tol : float in (0, 1), optional (default=0.1)
        The parameter to decide the flexibility while dealing
        the samples falling outside the bins.

    Returns
    -------
    outlier_scores : numpy array of shape (n_samples, n_features)
        Outlier scores on all features (dimensions).
    """

    n_samples, n_features = X.shape[0], X.shape[1]
    outlier_scores = np.zeros(shape=(n_samples, n_features))

    for i in range(n_features):

        # Find the indices of the bins to which each value belongs.
        # See documentation for np.digitize since it is tricky
        # >>> x = np.array([0.2, 6.4, 3.0, 1.6, -1, 100, 10])
        # >>> bins = np.array([0.0, 1.0, 2.5, 4.0, 10.0])
        # >>> np.digitize(x, bins, right=True)
        # array([1, 4, 3, 2, 0, 5, 4], dtype=int64)

        bin_inds = np.digitize(X[:, i], bin_edges[:, i], right=True)

        # Calculate the outlying scores on dimension i
        # Add a regularizer for preventing overflow
        out_score_i = np.log2(hist[:, i] + alpha)

        for j in range(n_samples):

            # If the sample does not belong to any bins
            # bin_ind == 0 (fall outside since it is too small)
            if bin_inds[j] == 0:
                dist = bin_edges[0, i] - X[j, i]
                bin_width = bin_edges[1, i] - bin_edges[0, i]

                # If it is only slightly lower than the smallest bin edge
                # assign it to bin 1
                if dist <= bin_width * tol:
                    outlier_scores[j, i] = out_score_i[0]
                else:
                    outlier_scores[j, i] = np.min(out_score_i)

            # If the sample does not belong to any bins
            # bin_ind == n_bins+1 (fall outside since it is too large)
            elif bin_inds[j] == n_bins + 1:
                dist = X[j, i] - bin_edges[-1, i]
                bin_width = bin_edges[-1, i] - bin_edges[-2, i]

                # If it is only slightly larger than the largest bin edge
                # assign it to the last bin
                if dist <= bin_width * tol:
                    outlier_scores[j, i] = out_score_i[n_bins - 1]
                else:
                    outlier_scores[j, i] = np.min(out_score_i)
            else:
                outlier_scores[j, i] = out_score_i[bin_inds[j] - 1]

    return outlier_scores


def invert_order(scores, method='multiplication'):
    """ Invert the order of a list of values. The smallest value becomes
    the largest in the inverted list. This is useful while combining
    multiple detectors since their score order could be different.
    
    Parameters
    ----------
    scores : list, array or numpy array with shape (n_samples,)
        The list of values to be inverted
    method : str, optional (default='multiplication')
        Methods used for order inversion. Valid methods are:
        - 'multiplication': multiply by -1
        - 'subtraction': max(scores) - scores
    Returns
    -------
    inverted_scores : numpy array of shape (n_samples,)
        The inverted list
    Examples
    --------
    >>> scores1 = [0.1, 0.3, 0.5, 0.7, 0.2, 0.1]
    >>> invert_order(scores1)
    array([-0.1, -0.3, -0.5, -0.7, -0.2, -0.1])
    >>> invert_order(scores1, method='subtraction')
    array([ 0.6,  0.4,  0.2,  0. ,  0.5,  0.6])
    """

    scores = column_or_1d(scores)

    if method == 'multiplication':
        return scores.ravel() * -1

    if method == 'subtraction':
        return (scores.max() - scores).ravel()

