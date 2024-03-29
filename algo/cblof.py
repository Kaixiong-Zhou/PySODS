import numpy as np
from algo.base import Base
from scipy.spatial.distance import cdist
from sklearn.cluster import KMeans
import warnings
from numpy import percentile


class CBLOF(Base):
    """The CBLOF operator calculates the outlier score based on cluster-based
    local outlier factor.
    CBLOF takes as an input the data set and the cluster model that was
    generated by a clustering algorithm. It classifies the clusters into small
    clusters and large clusters using the parameters alpha and beta.
    The anomaly score is then calculated based on the size of the cluster the
    point belongs to as well as the distance to the nearest large cluster.
    Use weighting for outlier factor based on the sizes of the clusters as
    proposed in the original publication. Since this might lead to unexpected
    behavior (outliers close to small clusters are not found), it is disabled
    by default.Outliers scores are solely computed based on their distance to
    the closest large cluster center.


    Parameters
    ----------
     n_clusters : int, optional (default=8)
        The number of clusters to form as well as the number of
        centroids to generate.

    contamination : float in (0., 0.5), optional (default=0.1)
        The amount of contamination of the data set,
        i.e. the proportion of outliers in the data set. Used when fitting to
        define the threshold on the decision function.

    clustering_estimator : Estimator, optional (default=None)
        The base clustering algorithm for performing data clustering.
        A valid clustering algorithm should be passed in. The estimator should
        have standard sklearn APIs, fit() and predict(). The estimator should
        have attributes ``labels_`` and ``cluster_centers_``.
        If ``cluster_centers_`` is not in the attributes once the model is fit,
        it is calculated as the mean of the samples in a cluster.
        If not set, CBLOF uses KMeans for scalability. See
        https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html

    alpha : float in (0.5, 1), optional (default=0.9)
        Coefficient for deciding small and large clusters. The ratio
        of the number of samples in large clusters to the number of samples in
        small clusters.

    beta : int or float in (1,), optional (default=5).
        Coefficient for deciding small and large clusters. For a list
        sorted clusters by size `|C1|, \|C2|, ..., |Cn|, beta = |Ck|/|Ck-1|`

    use_weights : bool, optional (default=False)
        If set to True, the size of clusters are used as weights in
        outlier score calculation.

    check_estimator : bool, optional (default=False)
        If set to True, check whether the base estimator is consistent with
        sklearn standard.

    """

    def __init__(self, n_clusters=8, contamination=0.1,
                 clustering_estimator=None, alpha=0.9, beta=5,
                 use_weights=False, random_state=None,
                 n_jobs=1):
        super(CBLOF, self).__init__()
        self.n_clusters = n_clusters
        self.clustering_estimator = clustering_estimator
        self.alpha = alpha
        self.beta = beta
        self.use_weights = use_weights
        self.random_state = random_state
        self.n_jobs = n_jobs
        self.contamination=contamination
        self.threshold = None

    # noinspection PyIncorrectDocstring
    def fit(self, X,y=None):
        """Fit detector.
        Parameters
        ----------
        X : dataframe of shape (n_samples, n_features)
            The input samples.
        """
        X=X.to_numpy()
        n_samples, n_features = X.shape

        self._validate_estimator(default=KMeans(
            n_clusters=self.n_clusters,
            random_state=self.random_state,
            n_jobs=self.n_jobs))

        self.clustering_estimator_.fit(X=X, y=y)
        self.cluster_labels_ = self.clustering_estimator_.labels_
        self.cluster_sizes_ = np.bincount(self.cluster_labels_)

        # Get the actual number of clusters
        self.n_clusters_ = self.cluster_sizes_.shape[0]

        if self.n_clusters_ != self.n_clusters:
            warnings.warn("The chosen clustering for CBLOF forms {0} clusters"
                          "which is inconsistent with n_clusters ({1}).".
                          format(self.n_clusters_, self.n_clusters))

        self._set_cluster_centers(X, n_features)
        self._set_small_large_clusters(n_samples)

        self.decision_scores_ = self._decision_function(X,
                                                        self.cluster_labels_)

        self._process_decision_scores()
        return

    def _validate_estimator(self, default=None):
        """Check the value of alpha and beta and clustering algorithm.
        """

        if self.clustering_estimator is not None:
            self.clustering_estimator_ = self.clustering_estimator
        else:
            self.clustering_estimator_ = default

        # make sure the base clustering algorithm is valid
        if self.clustering_estimator_ is None:
            raise ValueError("clustering algorithm cannot be None")

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

        self._mu = np.mean(self.decision_scores_)
        self._sigma = np.std(self.decision_scores_)

        return self

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
        X=X.to_numpy()
        labels = self.clustering_estimator_.predict(X)
        return self._decision_function(X, labels)
    def _set_cluster_centers(self, X, n_features):
        # Noted not all clustering algorithms have cluster_centers_
        if hasattr(self.clustering_estimator_, 'cluster_centers_'):
            self.cluster_centers_ = self.clustering_estimator_.cluster_centers_
        else:
            warnings.warn("The chosen clustering for CBLOF does not have"
                          "the center of clusters. Calculate the center"
                          "as the mean of the clusters.")
            self.cluster_centers_ = np.zeros([self.n_clusters_, n_features])
            for i in range(self.n_clusters_):
                self.cluster_centers_[i, :] = np.mean(
                    X[np.where(self.cluster_labels_ == i)], axis=0)

    def _set_small_large_clusters(self, n_samples):
        size_clusters = np.bincount(self.cluster_labels_)

        sorted_cluster_indices = np.argsort(size_clusters * -1)

        alpha_list = []
        beta_list = []

        for i in range(1, self.n_clusters_):
            temp_sum = np.sum(size_clusters[sorted_cluster_indices[:i]])
            if temp_sum >= n_samples * self.alpha:
                alpha_list.append(i)

            if size_clusters[sorted_cluster_indices[i - 1]] / size_clusters[
                sorted_cluster_indices[i]] >= self.beta:
                beta_list.append(i)
        intersection = np.intersect1d(alpha_list, beta_list)

        if len(intersection) > 0:
            self._clustering_threshold = intersection[0]
        elif len(alpha_list) > 0:
            self._clustering_threshold = alpha_list[0]
        elif len(beta_list) > 0:
            self._clustering_threshold = beta_list[0]
        else:
            raise ValueError("Could not form valid cluster separation. Please "
                             "change n_clusters or change clustering method")

        self.small_cluster_labels_ = sorted_cluster_indices[
                                     self._clustering_threshold:]
        self.large_cluster_labels_ = sorted_cluster_indices[
                                     0:self._clustering_threshold]

        self._large_cluster_centers = self.cluster_centers_[
            self.large_cluster_labels_]

    def _decision_function(self, X, labels):
        # Initialize the score array
        scores = np.zeros([X.shape[0], ])

        small_indices = np.where(
            np.isin(labels, self.small_cluster_labels_))[0]
        large_indices = np.where(
            np.isin(labels, self.large_cluster_labels_))[0]

        if small_indices.shape[0] != 0:
            dist_to_large_center = cdist(X[small_indices, :],
                                         self._large_cluster_centers)

            scores[small_indices] = np.min(dist_to_large_center, axis=1)

        if large_indices.shape[0] != 0:
            large_centers = self.cluster_centers_[labels[large_indices]]

            scores[large_indices] = pairwise_distances_no_broadcast(
                X[large_indices, :], large_centers)

        if self.use_weights:
            scores = scores * self.cluster_sizes_[labels]

        return scores.ravel()

def pairwise_distances_no_broadcast(X, Y):
    """Utility function to calculate row-wise euclidean distance of two matrix.
    Different from pair-wise calculation, this function would not broadcast.
    For instance, X and Y are both (4,3) matrices, the function would return
    a distance vector with shape (4,), instead of (4,4).
    Parameters
    ----------
    X : array of shape (n_samples, n_features)
        First input samples
    Y : array of shape (n_samples, n_features)
        Second input samples
    Returns
    -------
    distance : array of shape (n_samples,)
        Row-wise euclidean distance of X and Y
    """

    if X.shape[0] != Y.shape[0] or X.shape[1] != Y.shape[1]:
        raise ValueError("pairwise_distances_no_broadcast function receive"
                         "matrix with different shapes {0} and {1}".format(
            X.shape, Y.shape))
    return _pairwise_distances_no_broadcast_helper(X, Y)


def _pairwise_distances_no_broadcast_helper(X, Y):  # pragma: no cover
    """Internal function for calculating the distance with numba. Do not use.
    Parameters
    ----------
    X : array of shape (n_samples, n_features)
        First input samples
    Y : array of shape (n_samples, n_features)
        Second input samples
    Returns
    -------
    distance : array of shape (n_samples,)
        Intermediate results. Do not use.
    """
    euclidean_sq = np.square(Y - X)
    return np.sqrt(np.sum(euclidean_sq, axis=1)).ravel()

